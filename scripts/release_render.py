"""Deploy the checked-out commit and wait for Render to confirm that exact release."""

import json
import os
import re
import sys
import time
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(url, token=None, payload=None):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode()
    with build_opener(NoRedirect).open(
        Request(url, data=data, headers=headers), timeout=30
    ) as response:
        return json.load(response)


def release(preflight=False):
    service_id = os.environ["RENDER_SERVICE_ID"]
    sha = os.environ["GITHUB_SHA"]
    token = os.environ["RENDER_API_KEY"]
    backend = os.environ["TNR_BACKEND_URL"].rstrip("/")
    if not re.fullmatch(r"srv-[a-z0-9]+", service_id) or not re.fullmatch(r"[a-f0-9]{40}", sha):
        raise ValueError("Invalid service or commit")
    if not re.fullmatch(r"https://[a-z0-9-]+\.onrender\.com", backend):
        raise ValueError("Expected an HTTPS Render backend")
    endpoint = f"https://api.render.com/v1/services/{service_id}"
    service = request(endpoint, token)
    if service.get("autoDeploy") != "no" or service.get("branch") != "main":
        raise ValueError("Render must use main with Auto-Deploy Off")
    if service.get("serviceDetails", {}).get("url") != backend:
        raise ValueError("Backend URL does not match the Render service")
    if preflight:
        return
    # Never retry this POST: a timeout can mean the deployment was accepted.
    deployment = request(endpoint + "/deploys", token, {"commitId": sha})
    deploy_id = deployment["id"]
    if not re.fullmatch(r"dep-[a-z0-9]+", deploy_id):
        raise ValueError("Invalid deployment ID")
    print(f"Waiting for Render deployment {deploy_id}", flush=True)
    deadline = time.monotonic() + 1200
    while time.monotonic() < deadline:
        deployment = request(endpoint + "/deploys/" + deploy_id, token)
        status = deployment["status"]
        if status == "live":
            if deployment.get("commit", {}).get("id") != sha:
                raise RuntimeError("Render deployed a different commit")
            if request(backend + "/api/health") != {"status": "ok"}:
                raise RuntimeError("Backend health check failed")
            print("Render confirmed the requested commit and process health.")
            return
        if status in {
            "build_failed",
            "update_failed",
            "pre_deploy_failed",
            "canceled",
            "deactivated",
        }:
            raise RuntimeError("Render deployment did not succeed")
        time.sleep(10)
    raise TimeoutError("Render deployment timeout")


if __name__ == "__main__":
    try:
        release(preflight="--preflight" in sys.argv)
    except (OSError, ValueError, KeyError, RuntimeError):
        print(
            "Render release failed. Check the Render deployment before retrying.", file=sys.stderr
        )
        raise SystemExit(1) from None
