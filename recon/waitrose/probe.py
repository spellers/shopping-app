import json, urllib.request

GQL = "https://www.waitrose.com/api/graphql-prod/graph/live"
HDRS = {
    "Content-Type": "application/json",
    "User-Agent": "okhttp/4.12.0",
    "Authorization": "Bearer unauthenticated",
    "client-correlation-id": "probe-1",
    "breadcrumb": "android",
}

def gql(query, variables):
    req = urllib.request.Request(GQL, data=json.dumps({"query": query, "variables": variables}).encode(), headers=HDRS)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")

login_m = '''mutation NewSession($input: SessionInput) {
  generateSession(session: $input) { accessToken refreshToken customerId customerOrderId customerOrderState defaultBranchId expiresIn failures { type message } }
}'''
print("login:", gql(login_m, {"input": {"username": "probe@example.com", "password": "wrong", "clientId": "ANDROID_APP"}}))

# search needs customerId -> probe unauthenticated
body = json.dumps({"customerSearchRequest": {"queryParams": {"searchTerm": "milk", "start": 0}}}).encode()
req = urllib.request.Request("https://www.waitrose.com/api/content-prod/v2/cms/publish/productcontent/search/unauthenticated?clientType=WEB_APP", data=body, headers={**HDRS, "Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read())
        print("search unauth:", r.status, "totalMatches:", d.get("totalMatches"), "components:", len(d.get("componentsAndProducts") or []))
except urllib.error.HTTPError as e:
    print("search unauth:", e.code, e.read()[:300])
