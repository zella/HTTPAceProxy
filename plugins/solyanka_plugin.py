'''

Plugin for merging multiple m3u playlist into one.
Tv guid and grouping will work only for first playlist. Other playlists will be grouped by url hostname, eg "www.example.tv"

To access merged playlist, go to http://127.0.0.1:8000/solyanka/playlist.m3u
'''
from modules.PluginInterface import AceProxyPlugin

import requests
import time
import zlib

try:
    from urlparse import urlparse
except:
    from urllib.parse import urlparse
import config.solyanka as config


class Solyanka(AceProxyPlugin):
    handlers = ('solyanka',)

    playlist = None
    playlisttime = None

    def __init__(self, AceConfig, AceStuff):
        pass

    def prepare_m3u(self, header, m3u, tail):

        def update_extinf(ext_inf):
            splitted = ext_inf.split(',')
            name = splitted[1] if len(splitted) >= 2 else 'no name'
            if 'group-title' not in ext_inf.lower() or tail:
                return '#EXTINF:-1 group-title="%s",%s' % (header, name)
            else:
                return ext_inf

        by_lines = m3u.splitlines()
        transformed = []
        for line in by_lines:
            if line.startswith('#EXTINF'):
                ext_inf = update_extinf(line)
                transformed.append(ext_inf)
                if tail:
                    transformed.append("#EXTGRP:%s" % header)
            elif line.startswith('http'):
                transformed.append(line)
            elif line.startswith('#EXTM3U') and not tail:
                transformed.append(line)
        return '\n'.join(transformed)

    def download_playlist(self, url, tail):
        headers = {'User-Agent': 'Super Browser'}
        response = requests.get(url, headers=headers, proxies=config.proxies, stream=False, timeout=30)
        text = response.text if response.status_code == 200 else ''
        return self.prepare_m3u(urlparse(url).hostname.encode(), text, tail)

    def collect_playlists(self):
        Solyanka.playlisttime = int(time.time())
        head, tail = config.playlists_urls[0], config.playlists_urls[1:]
        head_playlist = self.download_playlist(head, tail=False)
        tail_playlists = list(map(lambda x: self.download_playlist(x, tail=True), tail))
        summary_playlists = [head_playlist] + tail_playlists
        Solyanka.playlist = '\n'.join(summary_playlists)
        return next((x for x in Solyanka.playlist.split('\n') if x.startswith('http')), None) is not None

    def handle(self, connection, headers_only=False):

        url = requests.compat.urlparse(connection.path)
        path = url.path[0:-1] if url.path.endswith('/') else url.path

        # 20 minutes cache
        if Solyanka.playlist is None or (int(time.time()) - Solyanka.playlisttime > 20 * 60):
            if not self.collect_playlists(): connection.dieWithError(); return

        if path == '/solyanka/playlist.m3u':
            data = Solyanka.playlist
            # TODO not modified status
            connection.send_response(200)
            connection.send_header('Content-Type', 'audio/mpegurl; charset=utf-8')
            try:
                h = connection.headers.get('Accept-Encoding').split(',')[0]
                compress_method = {'zlib': zlib.compressobj(9, zlib.DEFLATED, zlib.MAX_WBITS),
                                   'deflate': zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS),
                                   'gzip': zlib.compressobj(9, zlib.DEFLATED, zlib.MAX_WBITS | 16)}
                data = compress_method[h].compress(data) + compress_method[h].flush()
                connection.send_header('Content-Encoding', h)
            except:
                pass
            connection.send_header('Content-Length', len(data))
            connection.send_header('Connection', 'close')
            connection.end_headers()

            connection.wfile.write(data.encode())
        else:
            connection.send_response(400)
            connection.send_header('Connection', 'close')
            connection.end_headers()
