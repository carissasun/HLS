#!/usr/bin/env python
#import flask

import SimpleHTTPServer
import SocketServer
import food_scraper

__version__ = "0.6"

__all__ = ["SimpleHTTPRequestHandler"]

import os
import posixpath
import BaseHTTPServer
import urllib
import cgi
import sys
import shutil
import mimetypes
import datetime
import urlparse
import cgi
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

class FoodRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):

    """Simple HTTP request handler with GET and HEAD commands.
    This serves files from the current directory and any of its
    subdirectories.  The MIME type for files is determined by
    calling the .guess_type() method.
    The GET and HEAD requests are identical except that the HEAD
    request omits the actual contents of the file.
    """

    server_version = "SimpleHTTP/" + __version__
    day_cache = {}
    event_cache = {}

    def do_GET(self):
        """Serve a GET request."""
        f = self.send_head()
        if f:
            self.copyfile(f, self.wfile)
            f.close()

    def do_HEAD(self):
        """Serve a HEAD request."""
        f = self.send_head()
        if f:
            f.close()

    def send_head(self):
        """Common code for GET and HEAD commands.
        This sends the response code and MIME headers.
        Return value is either a file object (which has to be copied
        to the outputfile by the caller unless the command was HEAD,
        and must be closed by the caller under all circumstances), or
        None, in which case the caller has nothing further to do.
        """
        path = self.translate_path(self.path)
        f = None
        if os.path.isdir(path):
            if not self.path.endswith('/'):
                # redirect browser - doing basically what apache does
                self.send_response(301)
                self.send_header("Location", self.path + "/")
                self.end_headers()
                return None
            for index in "index.html", "index.htm":
                index = os.path.join(path, index)
                if os.path.exists(index):
                    path = index
                    break
            else:
                return self.list_events()
        ctype = self.guess_type(path)
        try:
            # Always read in binary mode. Opening files in text mode may cause
            # newline translations, making the actual size of the content
            # transmitted *less* than the content-length!
            f = open(path, 'rb')
        except IOError:
            self.send_error(404, "File not found")
            return None
        self.send_response(200)
        self.send_header("Content-type", ctype)
        fs = os.fstat(f.fileno())
        self.send_header("Content-Length", str(fs[6]))
        self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
        self.end_headers()
        return f

    def list_events(self):
        """Helper to produce a directory listing (absent index.html).
        Return value is either a file object, or None (indicating an
        error).  In either case, the headers are sent, making the
        interface the same as for send_head().
        """
        query = urlparse.urlparse(self.path).query
        components = urlparse.parse_qs(query)
        date = cgi.escape(components['date'][0] if 'date' in components else '')
        day_offset = 0
        try:
            day_offset = int(date[:len(date)-1])
        except ValueError:
            pass
        
        today = datetime.datetime.today()
        today = today + datetime.timedelta(days = day_offset)
        food = food_scraper.get_food_listings(today.date(), self.day_cache, self.event_cache)
        
        f = StringIO()
        displaypath = cgi.escape(urllib.unquote(self.path))
        f.write('<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">')
        f.write("<html>\n<title>Lunch!</title>\n")
        f.write("<body>\n<h2>Events for %s</h2>\n" % today.date())
        f.write("<hr>\n<h3>With food:</h3>\n")
        f.write("<ul>\n")
        for event in food['food']:
            f.write("<li>%s" % event.short_str())
            f.write("<ul><li>%s</li></ul>" % event.food)
            f.write("</li>")
        f.write("</ul>\n<hr>\n<h3>Other events:</h3>\n")
        f.write("<ul>\n")
        for event in food['nofood']:
            f.write("<li>%s</li>" % event.short_str())
        f.write("</ul>\n<hr>\n")
        f.write('<form action=".">')
        f.write('<input type="submit" value="Today" />')
        f.write('<input type="hidden" name="date" value="0">')
        f.write('</form>')
        f.write('<form action=".">')
        f.write('<input type="submit" value="Tomorrow" />')
        f.write('<input type="hidden" name="date" value="1">')
        f.write('</form>')
        f.write('<form action=".">')
        f.write('<input type="submit" value="2 days from now" />')
        f.write('<input type="hidden" name="date" value="2">')
        f.write('</form>\n')
        f.write("</body>\n</html>\n")
        length = f.tell()
        f.seek(0)
        self.send_response(200)
        encoding = sys.getfilesystemencoding()
        self.send_header("Content-type", "text/html; charset=%s" % encoding)
        self.send_header("Content-Length", str(length))
        self.end_headers()
        return f

    def translate_path(self, path):
        """Translate a /-separated PATH to the local filename syntax.
        Components that mean special things to the local file system
        (e.g. drive or directory names) are ignored.  (XXX They should
        probably be diagnosed.)
        """
        # abandon query parameters
        path = path.split('?',1)[0]
        path = path.split('#',1)[0]
        path = posixpath.normpath(urllib.unquote(path))
        words = path.split('/')
        words = filter(None, words)
        path = os.getcwd()
        for word in words:
            drive, word = os.path.splitdrive(word)
            head, word = os.path.split(word)
            if word in (os.curdir, os.pardir): continue
            path = os.path.join(path, word)
        return path

    def copyfile(self, source, outputfile):
        """Copy all data between two file objects.
        The SOURCE argument is a file object open for reading
        (or anything with a read() method) and the DESTINATION
        argument is a file object open for writing (or
        anything with a write() method).
        The only reason for overriding this would be to change
        the block size or perhaps to replace newlines by CRLF
        -- note however that this the default server uses this
        to copy binary data as well.
        """
        shutil.copyfileobj(source, outputfile)

    def guess_type(self, path):
        """Guess the type of a file.
        Argument is a PATH (a filename).
        Return value is a string of the form type/subtype,
        usable for a MIME Content-type header.
        The default implementation looks the file's extension
        up in the table self.extensions_map, using application/octet-stream
        as a default; however it would be permissible (if
        slow) to look inside the data to make a better guess.
        """

        base, ext = posixpath.splitext(path)
        if ext in self.extensions_map:
            return self.extensions_map[ext]
        ext = ext.lower()
        if ext in self.extensions_map:
            return self.extensions_map[ext]
        else:
            return self.extensions_map['']

    if not mimetypes.inited:
        mimetypes.init() # try to read system mime.types
    extensions_map = mimetypes.types_map.copy()
    extensions_map.update({
        '': 'application/octet-stream', # Default
        '.py': 'text/plain',
        '.c': 'text/plain',
        '.h': 'text/plain',
        })


def main():
    port = 8000

    handler = SimpleHTTPServer.SimpleHTTPRequestHandler
    #httpd = SocketServer.TCPServer(("", port), MyTCPHandler)
    httpd = SocketServer.TCPServer(("", port), FoodRequestHandler)
    print 'serving at port %d' % port
    httpd.serve_forever()

if __name__ == "__main__":
    main()
