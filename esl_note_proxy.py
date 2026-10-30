"""Mount the existing Note controller in ESL Hub without sharing its runtime."""
import ipaddress
from urllib.parse import quote, urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import Request, ProxyHandler, HTTPRedirectHandler, build_opener

from flask import Response, redirect, request


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


UPSTREAM = "http://127.0.0.1:29174"
ALLOWED_HOSTS = {"ronhub.local", "ronhub", "192.168.86.33", "192.168.220.1", "127.0.0.1", "localhost", "::1"}
LOCAL_NETWORKS = tuple(map(ipaddress.ip_network, ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "::1/128")))
REQUEST_HEADERS = ("Content-Type", "X-CSRF-Token", "Cookie", "Authorization", "If-None-Match", "X-Wake-Reason")
RESPONSE_HEADERS = {"content-type", "content-disposition", "cache-control", "content-security-policy", "x-content-type-options", "referrer-policy", "etag", "x-sleep-seconds", "x-server-time", "x-wake-schedule", "location", "set-cookie"}


def register_note_controller(app):
    opener=build_opener(ProxyHandler({}),NoRedirect())

    @app.route("/note",methods=["GET"])
    def note_redirect():
        return redirect("/note/")

    @app.route("/note/",defaults={"path":""},methods=["GET","POST"])
    @app.route("/note/<path:path>",methods=["GET","POST"])
    def note_controller(path):
        try:
            address=ipaddress.ip_address(request.remote_addr)
            local=any(address in network for network in LOCAL_NETWORKS)
        except (ValueError,TypeError):
            local=False
        if not local or urlsplit(request.host_url).hostname not in ALLOWED_HOSTS:
            return Response("Open Note calendar on your home network using ronhub.local:5000/note/.",403)
        if not path and request.method=="GET" and request.args.get("embedded")!="1":
            return redirect("/?tab=note4")
        if request.method=="POST" and request.headers.get("Origin") not in (None,request.host_url.rstrip("/")):
            return Response("Reload Note calendar and try again.",403)
        if request.content_length and request.content_length>32768:
            return Response("The upload is too large.",413)
        headers={name:request.headers[name] for name in REQUEST_HEADERS if name in request.headers}
        headers["X-Note-Mount"]="/note"
        headers["Accept-Encoding"]="identity"
        url=UPSTREAM+"/"+quote(path,safe="/")
        if request.query_string:
            url+="?"+request.query_string.decode("ascii")
        outgoing=Request(url,data=request.get_data() if request.method=="POST" else None,headers=headers,method=request.method)
        try:
            try:
                result=opener.open(outgoing,timeout=90)
            except HTTPError as error:
                result=error
            with result:
                response_headers=[(name,value) for name,value in result.headers.items() if name.lower() in RESPONSE_HEADERS]
                return Response(result.read(),status=result.code,headers=response_headers)
        except (URLError,TimeoutError,OSError):
            return Response("Note calendar is temporarily unavailable. Reload this page in a moment.",502,headers={"Cache-Control":"no-store"})
