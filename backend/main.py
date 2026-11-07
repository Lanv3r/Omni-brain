import os
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:3000"])
issues_url = os.getenv(
    "ISSUES_URL",
    "http://127.0.0.1:8080/api/v0/issues?status=open&class=Network&_limit=50&_page=0",
)


@app.get("/issues")
def issues():
    try:
        with urlopen(issues_url, timeout=10) as upstream:
            return Response(upstream.read(), media_type="application/json")
    except HTTPError as error:
        return Response(error.read(), status_code=error.code)
    except URLError as error:
        return Response(f"Could not reach issues API: {error.reason}", status_code=502)
