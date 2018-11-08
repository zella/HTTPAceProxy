'''

Plugin for merging multiple m3u playlist.
Tv guid and grouping will work only for first playlist. Other playlists will be grouped by url hostname, eg "www.example.tv"

To access merged playlist, go to http://127.0.0.1:8000/solyanka.m3u
'''
from modules.PluginInterface import AceProxyPlugin

import requests
import time
from itertools import chain

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

    def prepare_tail_m3u(self, header: bytes, m3u: bytes):
        def minify_extinf(extinf: bytes):
            splitted = extinf.split(b',')
            name = splitted[1] if len(splitted) >= 2 else b'no name'
            return b'#EXTINF:-1 group-title="%b", %b' % (header, name)

        by_lines = m3u.splitlines()
        transformed = []
        for line in by_lines:
            if line.startswith(b'#EXTINF'):
                ext_inf = minify_extinf(line)
                transformed.append(ext_inf)
                transformed.append(b"#EXTGRP:%b" % header)
            elif line.startswith(b'http'):
                transformed.append(line)
        return b'\n'.join(transformed)

    def download_playlist(self, url: str, tail: bool):
        headers = {'User-Agent': 'Super Browser'}
        response = requests.get(url, headers=headers, proxies=config.proxies, stream=False, timeout=30)
        content = response.content if response.status_code == 200 else ''
        return content if not tail else self.prepare_tail_m3u(urlparse(url).hostname.encode(), content)

    def collect_playlists(self):
        Solyanka.playlisttime = int(time.time())
        head, tail = config.playlists_urls[0], config.playlists_urls[1:]
        head_playlist = self.download_playlist(head, tail=False)
        tail_playlists = list(map(lambda x: self.download_playlist(x, tail=True), tail))
        summary_playlists = [head_playlist] + tail_playlists
        Solyanka.playlist = b'\n'.join(summary_playlists)
        # TODO not efficient
        return next((x for x in Solyanka.playlist.split(b'\n') if x.startswith(b'http')), None) is not None

    def handle(self, connection, headers_only=False):
        connection.send_response(200)

        if headers_only:
            connection.send_header('Connection', 'close')
            connection.end_headers()
            return

        # 15 minutes cache
        if Solyanka.playlist is None or (int(time.time()) - Solyanka.playlisttime > 15 * 60):
            if not self.collect_playlists(): connection.dieWithError(); return

        connection.send_header('Content-type', 'text/plain; charset=utf-8')
        connection.send_header('Content-Length', len(Solyanka.playlist))
        connection.end_headers()

        connection.wfile.write(Solyanka.playlist)
