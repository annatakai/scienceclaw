"""Playwright check of the served demo: screenshots, console errors, pan frame rate.
Usage: python3 demo/screenshots.py [url] [outdir]   (serve demo/site first). Needs: pip install playwright; playwright install chromium"""
import json, sys, time
from playwright.sync_api import sync_playwright

url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/"
out = sys.argv[2] if len(sys.argv) > 2 else "demo/shots"
errs, report = [], {}
with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    pg.on("console", lambda m: errs.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
    pg.on("pageerror", lambda e: errs.append(f"pageerror: {e}"))
    pg.goto(url); pg.wait_for_function("window.__dig && window.__dig.map && window.__dig.map.loaded()", timeout=60000)
    pg.wait_for_timeout(3500)
    def shot(n): pg.screenshot(path=f"{out}/{n}.png")
    shot("01_initial_1440")
    # city-wide vs street level
    pg.evaluate("__dig.map.jumpTo({zoom: 12.2})"); pg.wait_for_timeout(1500); shot("02_citywide")
    # replay: step to year 3 and capture mid-animation of year 4
    pg.evaluate("__dig.S.frame=3; __dig.S.phase=4; __dig.renderState()"); pg.wait_for_timeout(800)
    pg.click("#b-next"); pg.wait_for_timeout(500)
    pg.evaluate("document.activeElement.blur()"); pg.keyboard.press("Space"); pg.wait_for_timeout(2300); shot("03_mid_replay"); pg.keyboard.press("Space")
    pg.wait_for_timeout(500)
    # street level + selected feature
    i = pg.evaluate("(()=>{const f=__dig.map.querySourceFeatures('segs').filter(f=>f.properties.cls==='arterial'); return f.length? f[Math.floor(f.length/2)].id : 0})()")
    pg.evaluate(f"__dig.select({i}, true)"); pg.wait_for_timeout(2500); shot("04_street_selected_info")
    pg.click("[data-tab=compare]"); pg.wait_for_timeout(600); shot("05_compare")
    pg.hover("#hit", position={"x": 150, "y": 90}); pg.wait_for_timeout(300); shot("05b_compare_tooltip")
    pg.click("[data-tab=table]"); pg.wait_for_timeout(800); shot("06_table")
    pg.click("[data-tab=activity]"); pg.wait_for_timeout(300)
    # frame rate while panning at city zoom
    pg.evaluate("__dig.select(-1); __dig.map.jumpTo({zoom: 12.4})"); pg.wait_for_timeout(1500)
    fps = pg.evaluate("""() => new Promise(res => { let n = 0, t0 = performance.now(), dir = 1; const m = __dig.map;
      function f() { m.panBy([6 * dir, 3 * dir], {duration: 0}); n++; if (n % 60 === 0) dir = -dir; if (performance.now() - t0 < 3000) requestAnimationFrame(f); else res(n / ((performance.now() - t0) / 1000)); } f(); })""")
    report["pan_fps"] = round(fps, 1)
    # mobile layout
    mp = b.new_context(viewport={"width": 390, "height": 800}, device_scale_factor=2, is_mobile=True, has_touch=True).new_page()
    mp.on("console", lambda m: errs.append(f"mobile {m.type}: {m.text}") if m.type in ("error",) else None)
    mp.on("pageerror", lambda e: errs.append(f"mobile pageerror: {e}"))
    mp.goto(url); mp.wait_for_function("window.__dig && window.__dig.map && window.__dig.map.loaded()", timeout=60000); mp.wait_for_timeout(3000)
    mp.screenshot(path=f"{out}/07_mobile_390.png")
    mp.screenshot(path=f"{out}/07b_mobile_390_full.png", full_page=True)
    report["console"] = errs
    b.close()
print(json.dumps(report, indent=1))
