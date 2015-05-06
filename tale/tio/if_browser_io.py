# coding=utf-8
"""
Webbrowser based I/O for a single player ('if') story.

'Tale' mud driver, mudlib and interactive fiction framework
Copyright by Irmen de Jong (irmen@razorvine.net)
"""
from __future__ import absolute_import, print_function, division
from wsgiref.simple_server import make_server, WSGIRequestHandler
from wsgiref.validate import validator
import cgi
import json
import logging
from email.utils import formatdate, parsedate
from . import iobase
from . import vfs
from .styleaware_wrapper import tag_split_re
from .. import mud_context
from .. import __version__ as tale_version_str
try:
    from html import escape as html_escape
except ImportError:
    from cgi import escape as html_escape

__all__ = ["HttpIo"]


style_tags_html = {
    "<dim>": ("<span class='txt-dim'>", "</span>"),
    "<normal>": ("<span class='txt-normal'>", "</span>"),
    "<bright>": ("<span class='txt-bright'>", "</span>"),
    "<ul>": ("<span class='txt-ul'>", "</span>"),
    "<it>": ("<span class='txt-it'>", "</span>"),
    "<rev>": ("<span class='txt-rev'>", "</span>"),
    "</>": None,
    "<living>": ("<span class='txt-living'>", "</span>"),
    "<player>": ("<span class='txt-player'>", "</span>"),
    "<item>": ("<span class='txt-item'>", "</span>"),
    "<exit>": ("<span class='txt-exit'>", "</span>"),
    "<location>": ("<span class='txt-location'>", "</span>"),
    "<monospaced>": ("<span class='txt-monospaced'>", "</span>")
}


def singlyfy_parameters(parameters):
    """
    Makes a cgi-parsed parameter dictionary into a dict where the values that
    are just a list of a single value, are converted to just that single value.
    """
    for key, value in parameters.items():
        if isinstance(value, (list, tuple)) and len(value) == 1:
            parameters[key] = value[0]
    return parameters


class CustomRequestHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        msg = format % args
        logging.getLogger("tale.wsgi").debug(msg)


class HttpIo(iobase.IoAdapterBase):
    """
    I/O adapter for a http/browser based interface.
    This doubles as a wsgi app and runs as a web server using wsgiref
    """
    def __init__(self, player_connection):
        super(HttpIo, self).__init__(player_connection)
        self.port = 8080
        self.server = make_server("localhost", self.port, app=validator(self.wsgi_app), handler_class=CustomRequestHandler)
        self.server.timeout = 0.5
        self.completer = None
        self.text_to_browser = []

    def __repr__(self):
        return "<HttpIo @ 0x%x, port %d>" % (id(self), self.port)

    def mainloop(self, player_connection):
        import webbrowser
        from threading import Thread
        url = "http://%s:%d/tale/" % self.server.server_address
        print("\nPoint your browser to the following url: ", url, end="\n\n")
        t = Thread(target=webbrowser.open, args=(url, ))
        t.start()
        while not self.stop_main_loop:
            self.server.handle_request()
        print("Game shutting down.")

    def pause(self, unpause=False):
        pass

    def install_tab_completion(self, completer):
        self.completer = completer

    def render_output(self, paragraphs, **params):
        for text, formatted in paragraphs:
            text = self.convert_to_html(text)
            if text == "\n":
                text = "<br>"
            if formatted:
                self.text_to_browser.append("<p>" + text + "</p>\n")
            else:
                self.text_to_browser.append("<pre>" + text + "</pre>\n")

    def output(self, *lines):
        for line in lines:
            self.output_no_newline(line)

    def output_no_newline(self, text):
        text = self.convert_to_html(text)
        if text == "\n":
            text = "<br>"
        self.text_to_browser.append("<p>" + text + "</p>\n")

    # ---- wsgi methods below -----

    def wsgi_app(self, environ, start_response):
        method = environ.get("REQUEST_METHOD")
        path = environ.get('PATH_INFO', '').lstrip('/')
        if not path:
            return self.wsgi_redirect(start_response, "/tale/")
        if path.startswith("tale/"):
            if method in ("GET", "POST"):
                parameters = singlyfy_parameters(cgi.parse(environ['wsgi.input'], environ))
                return self.wsgi_route(environ, path[5:], parameters, start_response)
            else:
                return self.wsgi_invalid_request(start_response)
        return self.wsgi_not_found(start_response)

    def wsgi_route(self, environ, path, parameters, start_response):
        if not path or path == "start":
            return self.wsgi_handle_start(environ, parameters, start_response)
        elif path == "about":
            return self.wsgi_handle_about(environ, parameters, start_response)
        elif path == "story":
            return self.wsgi_handle_story(environ, parameters, start_response)
        elif path == "text":
            return self.wsgi_handle_text(environ, parameters, start_response)
        elif path == "tabcomplete":
            return self.wsgi_handle_tabcomplete(environ, parameters, start_response)
        elif path == "input":
            return self.wsgi_handle_input(environ, parameters, start_response)
        elif path.startswith("static/"):
            return self.wsgi_handle_static(environ, path, start_response)
        return self.wsgi_not_found(start_response)

    def wsgi_invalid_request(self, start_response):
        """Called if invalid http method."""
        start_response('405 Method Not Allowed', [('Content-Type', 'text/plain')])
        return [b'Error 405: Method Not Allowed']

    def wsgi_not_found(self, start_response):
        """Called if Url not found."""
        start_response('404 Not Found', [('Content-Type', 'text/plain')])
        return [b'Error 404: Not Found']

    def wsgi_redirect(self, start_response, target):
        """Called to do a redirect"""
        start_response('302 Found', [('Location', target)])
        return []

    def wsgi_redirect_other(self, start_response, target):
        """Called to do a redirect see-other"""
        start_response('303 See Other', [('Location', target)])
        return []

    def wsgi_not_modified(self, start_response):
        """Called to signal that a resource wasn't modified"""
        start_response('304 Not Modified', [])
        return []

    def wsgi_handle_start(self, environ, parameters, start_response):
        # start page / titlepage
        headers = [('Content-Type', 'text/html; charset=utf-8')]
        etag = str(id(self.player_connection)) + "-" + str(mud_context.driver.server_started.timestamp())
        if_none = environ.get('HTTP_IF_NONE_MATCH')
        if if_none and (if_none == '*' or etag in if_none):
            return self.wsgi_not_modified(start_response)
        headers.append(("ETag", etag))
        start_response("200 OK", headers)
        resource = vfs.internal_resources["web/index.html"]
        txt = resource.data.format(story_version=mud_context.driver.config.version,
                                   story_name=mud_context.driver.config.name,
                                   story_author=mud_context.driver.config.author,
                                   story_author_email=mud_context.driver.config.author_address)
        return [txt.encode("utf-8")]

    def wsgi_handle_about(self, environ, parameters, start_response):
        # about page
        start_response("200 OK", [('Content-Type', 'text/html; charset=utf-8')])
        resource = vfs.internal_resources["web/about.html"]
        txt = resource.data.format(tale_version=tale_version_str,
                                   story_version=mud_context.driver.config.version,
                                   story_name=mud_context.driver.config.name,
                                   uptime="%d:%02d:%02d" % mud_context.driver.uptime,
                                   starttime=mud_context.driver.server_started,
                                   num_players=len(mud_context.driver.all_players))
        return [txt.encode("utf-8")]

    def wsgi_handle_story(self, environ, parameters, start_response):
        headers = [('Content-Type', 'text/html; charset=utf-8')]
        resource = vfs.internal_resources["web/story.html"]
        etag = str(id(self.player_connection)) + "-" + str(mud_context.driver.server_started.timestamp())
        if_none = environ.get('HTTP_IF_NONE_MATCH')
        if if_none and (if_none == '*' or etag in if_none):
            return self.wsgi_not_modified(start_response)
        headers.append(("ETag", etag))
        start_response('200 OK', headers)
        txt = resource.data.format(story_version=mud_context.driver.config.version,
                                   story_name=mud_context.driver.config.name,
                                   story_author=mud_context.driver.config.author,
                                   story_author_email=mud_context.driver.config.author_address)
        return [txt.encode("utf-8")]

    def wsgi_handle_text(self, environ, parameters, start_response):
        text = self.text_to_browser
        self.text_to_browser = []
        start_response('200 OK', [('Content-Type', 'application/json; charset=utf-8'),
                                  ('Cache-Control', 'no-cache, no-store, must-revalidate'),
                                  ('Pragma', 'no-cache'),
                                  ('Expires', '0')])
        response = {"text": "\n".join(text)}
        if text:
            response["turns"] = self.player_connection.player.turns
            response["location"] = self.player_connection.player.location.title
        return [json.dumps(response).encode("utf-8")]

    def wsgi_handle_tabcomplete(self, environ, parameters, start_response):
        start_response('200 OK', [('Content-Type', 'application/json; charset=utf-8'),
                                  ('Cache-Control', 'no-cache, no-store, must-revalidate'),
                                  ('Pragma', 'no-cache'),
                                  ('Expires', '0')])
        return [json.dumps(self.completer.complete(parameters["prefix"])).encode("utf-8")]

    def wsgi_handle_input(self, environ, parameters, start_response):
        cmd = parameters.get("cmd", "")
        if cmd and "autocomplete" in parameters:
            suggestions = self.completer.complete(cmd)
            if suggestions:
                self.text_to_browser.append("<p>Suggestions: " + ", ".join(suggestions) + "</p>")
            else:
                self.text_to_browser.append("<p>No matching commands.</p>")
        else:
            cmd = html_escape(cmd, False)
            if cmd:
                self.text_to_browser.append("<span class='txt-userinput'>%s</span>" % cmd)
            self.player_connection.player.store_input_line(cmd)
        start_response('200 OK', [('Content-Type', 'text/plain')])
        return []

    def wsgi_handle_static(self, environ, path, start_response):
        path = path[len("static/"):]
        if not self.wsgi_is_asset_allowed(path):
            return self.wsgi_not_found(start_response)
        try:
            return self.wsgi_serve_static("web/" + path, environ, start_response)
        except IOError:
            return self.wsgi_not_found(start_response)

    def wsgi_is_asset_allowed(self, path):
        return path.endswith(".html") or path.endswith(".js") or path.endswith(".jpg") \
            or path.endswith(".png") or path.endswith(".gif") or path.endswith(".css") or path.endswith(".ico")

    def wsgi_serve_static(self, path, environ, start_response):
        headers = []
        resource = vfs.internal_resources[path]
        if resource.mtime:
            mtime_formatted = formatdate(resource.mtime)
            etag = str(resource.mtime)
            if_modified = environ.get('HTTP_IF_MODIFIED_SINCE')
            if if_modified:
                if parsedate(if_modified) >= parsedate(mtime_formatted):
                    # the resource wasn't modified since last requested
                    return self.wsgi_not_modified(start_response)
            if_none = environ.get('HTTP_IF_NONE_MATCH')
            if if_none and (if_none == '*' or etag in if_none):
                return self.wsgi_not_modified(start_response)
            headers.append(("ETag", etag))
            headers.append(("Last-Modified", formatdate(resource.mtime)))
        if type(resource.data) is bytes:
            headers.append(('Content-Type', resource.mimetype))
            data = resource.data
        else:
            headers.append(('Content-Type', resource.mimetype + "; charset=utf-8"))
            data = resource.data.encode("utf-8")
        start_response('200 OK', headers)
        return [data]

    def convert_to_html(self, line):
        """Convert style tags to html"""
        chunks = tag_split_re.split(line)
        if len(chunks) == 1:
            # optimization in case there are no markup tags in the text at all
            return html_escape(self.smartquotes(line), False)
        result = []
        close_tags_stack = []
        chunks.append("</>")   # add a reset-all-styles sentinel
        for chunk in chunks:
            html_tags = style_tags_html.get(chunk)
            if html_tags:
                chunk = html_tags[0]
                close_tags_stack.append(html_tags[1])
            elif chunk == "</>":
                while close_tags_stack:
                    result.append(close_tags_stack.pop())
                continue
            elif chunk:
                if chunk.startswith("</"):
                    chunk = "<" + chunk[2:]
                    html_tags = style_tags_html.get(chunk)
                    if html_tags:
                        chunk = html_tags[1]
                        if close_tags_stack:
                            close_tags_stack.pop()
                else:
                    # normal text (not a tag)
                    chunk = html_escape(self.smartquotes(chunk), False)
            result.append(chunk)
        return "".join(result)