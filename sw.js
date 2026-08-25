/* THE ELSE EFFECT - offline safety net
   ------------------------------------------------------------------
   The screen loads from the web so it can be updated from a desk
   rather than by carrying a keyboard down a hallway. The cost of that
   is a dependency on the network being up at the moment the page
   reloads. This removes that cost.

   Strategy is network first, cache second. Every load tries the live
   file, so a change published from GitHub appears on the next reload.
   If the network is unreachable, the last good copy is served from
   cache instead and the screen keeps playing as though nothing
   happened.
   ------------------------------------------------------------------ */

var CACHE = "else-effect-v1";

self.addEventListener("install", function (e) {
  self.skipWaiting();
  e.waitUntil(
    caches.open(CACHE).then(function (c) {
      return c.add(new Request("./", { cache: "reload" }));
    }).catch(function () { /* first run with no network: nothing to warm */ })
  );
});

self.addEventListener("activate", function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (k) {
        return k === CACHE ? null : caches.delete(k);
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function (e) {
  if (e.request.method !== "GET") return;

  e.respondWith(
    fetch(e.request).then(function (res) {
      /* Only cache a real success. An error page or a captive portal
         redirect must never be allowed to overwrite a working copy. */
      if (res && res.ok && res.type !== "opaque") {
        var copy = res.clone();
        caches.open(CACHE).then(function (c) { c.put(e.request, copy); });
      }
      return res;
    }).catch(function () {
      return caches.match(e.request).then(function (hit) {
        return hit || caches.match("./");
      });
    })
  );
});
