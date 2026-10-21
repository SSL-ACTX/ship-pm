/**
 * Cloudflare Worker: ship-registry-bridge (Service Worker Syntax)
 * No build process or wrangler required. Paste directly into the browser editor.
 */

// Simple in-memory rate limiting map
const rateLimitMap = new Map();

function isRateLimited(ip, limit = 15, windowMs = 60000) {
  const now = Date.now();
  const record = rateLimitMap.get(ip) || { count: 0, reset: now + windowMs };

  if (now > record.reset) {
    record.count = 0;
    record.reset = now + windowMs;
  }

  record.count++;
  rateLimitMap.set(ip, record);
  return record.count > limit;
}

addEventListener("fetch", (event) => {
  event.respondWith(handleRequest(event.request));
});

async function handleRequest(request) {
  // 1. Only allow POST requests
  if (request.method !== "POST") {
    return new Response(JSON.stringify({ error: "Method Not Allowed" }), {
      status: 405,
      headers: { "Content-Type": "application/json" }
    });
  }

  // 2. Rate limiting check
  const clientIP = request.headers.get("CF-Connecting-IP") || "anonymous";
  if (isRateLimited(clientIP, 15, 60000)) {
    return new Response(JSON.stringify({ error: "Rate limit exceeded. Try again later." }), {
      status: 429,
      headers: { "Content-Type": "application/json" }
    });
  }

  try {
    const body = await request.json();
    const repo = body.repo;
    const tag = body.tag || "latest";

    // 3. Strict format validation: must be "owner/repo"
    if (typeof repo !== "string" || !/^[a-zA-Z0-9._-]+\/[a-zA-Z0-9._-]+$/.test(repo)) {
      return new Response(
        JSON.stringify({ error: "Invalid repository format. Must be 'owner/repo'." }),
        { status: 400, headers: { "Content-Type": "application/json" } }
      );
    }

    if (typeof tag !== "string" || !/^[a-zA-Z0-9._-]+$/.test(tag)) {
      return new Response(JSON.stringify({ error: "Invalid release tag." }), {
        status: 400,
        headers: { "Content-Type": "application/json" }
      });
    }

    // The caller proves its identity with a GitHub CLI token. The token is
    // validated here, used for read-only lookups, and never forwarded or saved.
    const authorization = request.headers.get("Authorization") || "";
    const tokenMatch = authorization.match(/^Bearer\s+(.+)$/i);
    if (!tokenMatch) {
      return new Response(JSON.stringify({ error: "GitHub authentication is required. Run `ship auth login`." }), {
        status: 401,
        headers: { "Content-Type": "application/json" }
      });
    }
    const userToken = tokenMatch[1].trim();
    const githubHeaders = {
      "Accept": "application/vnd.github+json",
      "Authorization": "Bearer " + userToken,
      "User-Agent": "ship-registry-bridge",
      "X-GitHub-Api-Version": "2022-11-28"
    };
    const identityResponse = await fetch("https://api.github.com/user", {
      headers: githubHeaders
    });
    if (!identityResponse.ok) {
      return new Response(JSON.stringify({ error: "GitHub rejected the credential. Run `gh auth login` again." }), {
        status: 401,
        headers: { "Content-Type": "application/json" }
      });
    }
    const identity = await identityResponse.json();
    if (!Number.isInteger(identity.id) || !/^[A-Za-z0-9-]{1,39}$/.test(identity.login || "")) {
      return new Response(JSON.stringify({ error: "GitHub returned an invalid user identity." }), {
        status: 502,
        headers: { "Content-Type": "application/json" }
      });
    }

    // GitHub's repository response reports the authenticated user's access.
    // write/admin/maintain contributors receive a trusted label in the PR;
    // other authenticated publishers can still submit for manual review.
    let upstreamPermission = "unknown";
    const upstreamResponse = await fetch("https://api.github.com/repos/" + repo, {
      headers: githubHeaders
    });
    if (upstreamResponse.ok) {
      const upstream = await upstreamResponse.json();
      const permissions = upstream.permissions || {};
      if (permissions.admin) {
        upstreamPermission = "admin";
      } else if (permissions.maintain) {
        upstreamPermission = "maintain";
      } else if (permissions.push) {
        upstreamPermission = "write";
      } else if (permissions.pull) {
        upstreamPermission = "read";
      } else {
        upstreamPermission = "none";
      }
    }

    // 4. In Service Worker syntax, environment variables are global variables:
    // Make sure REGISTRY_REPO and GH_DISPATCH_TOKEN are defined in Worker Settings -> Variables
    const targetRepo = typeof REGISTRY_REPO !== "undefined" ? REGISTRY_REPO : "SSL-ACTX/ship-pm";
    const token = typeof GH_DISPATCH_TOKEN !== "undefined" ? GH_DISPATCH_TOKEN : "";

    if (!token) {
      return new Response(
        JSON.stringify({ error: "Worker misconfigured: GH_DISPATCH_TOKEN secret is missing." }),
        { status: 500, headers: { "Content-Type": "application/json" } }
      );
    }

    const ghUrl = "https://api.github.com/repos/" + targetRepo + "/dispatches";

    // 5. Send repository_dispatch to GitHub
    const ghResponse = await fetch(ghUrl, {
      method: "POST",
      headers: {
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "User-Agent": "ship-registry-worker",
        "X-GitHub-Api-Version": "2022-11-28"
      },
      body: JSON.stringify({
        event_type: "register-release",
        client_payload: {
          repo: repo,
          tag: tag,
          requester_login: identity.login,
          requester_id: identity.id,
          upstream_permission: upstreamPermission
        }
      })
    });

    if (ghResponse.status === 204 || ghResponse.ok) {
      return new Response(
        JSON.stringify({
          status: "success",
          message: "Release queued for registration: " + repo + "@" + tag,
          requester: identity.login,
          upstream_permission: upstreamPermission
        }),
        { status: 202, headers: { "Content-Type": "application/json" } }
      );
    } else {
      const errText = await ghResponse.text();
      return new Response(
        JSON.stringify({ error: "Failed to dispatch to GitHub", details: errText }),
        { status: 502, headers: { "Content-Type": "application/json" } }
      );
    }
  } catch (err) {
    return new Response(
      JSON.stringify({ error: "Invalid JSON or server error", details: err.message }),
      { status: 400, headers: { "Content-Type": "application/json" } }
    );
  }
}
