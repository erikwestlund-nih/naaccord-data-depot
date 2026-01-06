# NPM SimpleSAMLphp Configuration (Staging Only)

## Problem
In staging, Nginx Proxy Manager (NPM) handles SSL termination and sits in front of the nginx container. NPM returns 404 for `/simplesaml/*` requests because it doesn't know to proxy them.

In production, there is no NPM - nginx handles SSL directly with Let's Encrypt, so this isn't an issue.

## Solution: Add Custom Location in NPM

1. **Log into NPM**: http://70.22.166.28:81
   - Default credentials: admin@example.com / changeme

2. **Edit Proxy Host**: Find `naaccord.pequod.sh` in proxy hosts

3. **Add Custom Location**:
   - Click on the proxy host
   - Go to "Custom Locations" tab
   - Click "Add Custom Location"
   - Configure:
     ```
     Define Location: /simplesaml/
     Scheme: http
     Forward Hostname/IP: 192.168.50.10
     Forward Port: 8080
     Forward Path: /simplesaml/
     ```
   - Check: "Websockets Support" (optional)
   - Save

4. **Test**: https://naaccord.pequod.sh/simplesaml/

## Why This Works

- **Staging**: Browser → NPM (SSL) → mock-idp:8080 directly
- **Production**: Browser → nginx (SSL) → (no mock-idp, uses JHU Shibboleth)

The custom location in NPM bypasses the nginx container entirely for `/simplesaml/*` paths, sending requests directly to the mock-idp container.

## Production Differences

In production:
- No NPM (nginx handles SSL with Let's Encrypt)
- No mock-idp container (uses JHU Shibboleth)
- SAML metadata URL points to JHU instead of local file
