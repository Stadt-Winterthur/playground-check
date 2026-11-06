/* Real templates/CSS/scripts, synthetic data only. No deployment side effects. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const { spawn } = require('node:child_process');
(async () => {
  const root = path.resolve(__dirname, '../..');
  const server = spawn(process.env.PYTHON || 'python', [path.join(__dirname, 'serve_fixtures.py')], {
    cwd: root, env: { ...process.env, PYTHONPATH: path.join(root, 'src') }, stdio: ['ignore', 'pipe', 'inherit']
  });
  let browser;
  try {
    const port = await new Promise((resolve, reject) => {
      let buffer = '';
      server.stdout.on('data', chunk => { buffer += chunk; if (buffer.includes('\n')) resolve(Number(buffer.split('\n')[0])); });
      server.on('exit', code => reject(new Error('Fixture server stopped: ' + code)));
    });
    browser = await chromium.launch({
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || undefined,
      headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
    });
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('dialog', dialog => dialog.accept());
    const base = `http://127.0.0.1:${port}/test-app`;
    // Chromium must accept the manifest and control the application subpath.
    await page.goto(`${base}/`);
    const cdp = await page.context().newCDPSession(page);
    const manifestResult = await cdp.send('Page.getAppManifest');
    assert.deepEqual(manifestResult.errors, [], 'Manifest rejected by Chromium');
    assert.equal(manifestResult.url, `${base}/manifest.webmanifest`);
    const manifest = JSON.parse(manifestResult.data);
    for (const field of ['start_url', 'scope']) {
      assert.equal(new URL(manifest[field], manifestResult.url).href, `${base}/`);
    }
    for (const size of ['192x192', '512x512']) {
      const icon = manifest.icons.find(icon => icon.sizes === size);
      const response = await page.request.get(new URL(icon.src, manifestResult.url).href);
      assert.equal(response.status(), 200);
      assert.match(response.headers()['content-type'], /image\/png/);
    }
    const scope = await page.evaluate(async () => {
      const registration = await navigator.serviceWorker.ready;
      return registration.scope;
    });
    assert.equal(scope, `${base}/`);
    await page.waitForFunction(() => navigator.serviceWorker.controller !== null);
    const installability = await cdp.send('Page.getInstallabilityErrors');
    assert.deepEqual(installability.installabilityErrors, [], 'Chromium installation requirements failed');
    console.log('Manifest, icons, service worker and Chromium installation requirements passed.');
    // SVG symbols must render from this app under its reverse-proxy prefix.
    for (const width of [320, 390, 1280]) {
      await page.setViewportSize({width, height:844});
      await page.goto(`${base}/home-private.html`);
      await page.locator('.user-menu summary').click();
      const icons = await page.locator('.ui-icon:visible').evaluateAll(nodes => nodes.map(svg => ({
        href:svg.querySelector('use').getAttribute('href'),
        width:svg.getBoundingClientRect().width,
        height:svg.getBoundingClientRect().height,
        geometry:svg.getBBox().width,
        hidden:svg.getAttribute('aria-hidden')
      })));
      assert.ok(icons.length >= 8, `Missing icons at ${width}px`);
      for (const icon of icons) {
        assert.ok(icon.href.startsWith('/test-app/static/vendor/lucide/sprite.svg#'));
        assert.equal(icon.width, 24);
        assert.equal(icon.height, 24);
        assert.ok(icon.geometry > 0, `Empty SVG symbol: ${icon.href}`);
        assert.equal(icon.hidden, 'true');
      }
      if (process.env.BROWSER_ARTIFACT_DIR) {
        await page.screenshot({path:path.join(process.env.BROWSER_ARTIFACT_DIR, `lucide-${width}.png`)});
      }
    }
    const names = ['home','home-private','login','profile','profile-long','detail','assigned','defect','defects','admin','inspection','create-defect'];
    const sizes = [[320,568],[360,800],[390,844],[640,800],[768,1024],[999,800],[1000,800],[1024,768],[1280,800],[1440,900],[667,375],[844,390]];
    let checked = 0;
    for (const [width,height] of sizes) {
      await page.setViewportSize({width,height});
      for (const name of names) {
        await page.goto(`${base}/${name}.html`);
        const dims = await page.evaluate(() => ({width:document.documentElement.clientWidth,
          scroll:document.documentElement.scrollWidth, main:document.querySelector('main').getBoundingClientRect().width}));
        assert.ok(dims.scroll <= dims.width + 1, `${name} ${width} overflows: ${JSON.stringify(dims)}`);
        if (['home','login'].includes(name) && width >= 1000) assert.ok(dims.main >= 500, `${name} desktop main collapsed`);
        checked++;
      }
    }
    await page.setViewportSize({width:390,height:844});
    await page.goto(`${base}/admin.html`);
    assert.equal(await page.locator('form[data-logout] button:visible').count(),0);
    assert.equal(await page.locator('.user-menu .menu-popover form[data-logout]').count(),1);
    assert.equal(await page.locator('form[data-logout]').getAttribute('action'),'/test-app/logout/');
    await page.locator('.user-menu summary').click();
    assert.equal(await page.locator(`a[href="/test-app/admin/users/"]:visible`).count(),1);
    assert.equal(await page.locator('form[data-logout] button:visible').count(),1);
    await page.goto(`${base}/create-defect.html`);
    assert.equal(await page.locator('[name=playdeviceFid]').inputValue(),'42');
    assert.equal(await page.locator('form[hx-post]').count(),0);
    await page.route('**/Playdevice/43/Picture/', route => route.fulfill({status:503,body:'Unavailable'}));
    await page.goto(`${base}/detail.html`);
    await page.locator('img[src$="no-device-photo.svg"]').first().waitFor();
    assert.ok(await page.locator('img[src$="no-device-photo.svg"]').count() >= 1);
    await page.locator('label[for=playground-tab-documents]').click();
    assert.equal(await page.locator('.playground-tab-documents').isVisible(),true);
    await page.goto(`${base}/inspection.html`);
    await page.locator('[data-inspection-select]').first().click();
    assert.equal(await page.locator('[data-inspection-device]:visible').count(),1);
    await page.locator('.inspection-device:visible .inspection-criterion summary').first().click();
    await page.locator('textarea[name^=comment_]').first().fill('Entwurf bleibt erhalten');
    await page.locator('[data-inspection-back]:visible').first().click();
    await page.locator('[data-inspection-select]').first().click();
    assert.equal(await page.locator('textarea[name^=comment_]').first().inputValue(),'Entwurf bleibt erhalten');
    await page.reload();
    assert.equal(await page.locator('textarea[name^=comment_]').first().inputValue(),'Entwurf bleibt erhalten');
    // Bulk actions also persist; status must be refreshed after draft restore.
    assert.equal(await page.locator('.inspection-device-head .inspection-device-chip').count(),0);
    await page.locator('[data-inspection-back]:visible').first().click();
    await page.locator('[data-inspection-chip]').first().click();
    await page.reload();
    assert.equal(await page.locator('[data-inspection-chip]').first().innerText(),'erledigt');
    await page.locator('[data-inspection-select]').first().click();
    assert.equal(await page.locator('input[name=inspection_done_42_0]').isChecked(),true);
    await page.goto(`${base}/inspection-success.html`);
    assert.equal(await page.evaluate(() => Object.keys(sessionStorage).filter(k=>k.startsWith('spk-inspection-draft:')).length),0);
    const noJS = await browser.newPage({javaScriptEnabled:false,viewport:{width:390,height:844}});
    await noJS.goto(`${base}/inspection.html`);
    assert.equal(await noJS.locator('[data-inspection-device]:visible').count(),0);
    await noJS.locator('[data-inspection-select]').first().click();
    assert.equal(await noJS.locator('[data-inspection-device]:visible').count(),1);
    await noJS.locator('.inspection-device:visible .inspection-criterion summary').first().click();
    await noJS.locator('textarea[name^=comment_]').first().fill('Ohne JavaScript erhalten');
    await noJS.locator('[data-inspection-back]').click();
    await noJS.locator('[data-inspection-select]').first().click();
    assert.equal(await noJS.locator('textarea[name^=comment_]').first().inputValue(),'Ohne JavaScript erhalten');
    await noJS.locator('[data-inspection-back]').click();
    assert.equal(await noJS.locator('#inspection-submit:visible').count(),1);
    assert.deepEqual(errors,[]);
    console.log(`${checked} layout states passed; navigation, device context, drafts, status restore and no-JS checks passed.`);
  } finally {
    if (browser) await browser.close();
    server.kill();
  }
})().catch(error => { console.error(error); process.exitCode=1; });
