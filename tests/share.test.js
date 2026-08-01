const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('static/share.js', 'utf8');
function loadShare(overrides = {}) {
    const context = { module: { exports: {} }, URL, prompt: () => {}, ...overrides };
    vm.runInNewContext(source, context);
    return { share: context.module.exports, context };
}

const { share, context } = loadShare({
    navigator: { clipboard: { writeText: async value => { context.copied = value; } } },
});

const pageUrl = share.buildPublicUrl({ href: 'https://panss.dpdns.org/static/index.html#results' }, 'python');
assert.equal(pageUrl, 'https://panss.dpdns.org/static/index.html?kw=python');
const xUrl = new URL(share.buildShareUrl('x', pageUrl, 'PanSou 搜索结果：python'));
assert.equal(`${xUrl.origin}${xUrl.pathname}`, 'https://twitter.com/intent/tweet');
assert.equal(xUrl.searchParams.get('url'), pageUrl);
const whatsappUrl = new URL(share.buildShareUrl('whatsapp', pageUrl, 'PanSou：网盘资源搜索工具'));
assert.equal(`${whatsappUrl.origin}${whatsappUrl.pathname}`, 'https://api.whatsapp.com/send');
assert.match(whatsappUrl.searchParams.get('text'), /PanSou：网盘资源搜索工具/);
assert.match(whatsappUrl.searchParams.get('text'), /https:\/\/panss\.dpdns\.org/);

(async () => {
    const native = loadShare({ navigator: { share: async () => {} } });
    assert.equal(await native.share.shareToWeChat(pageUrl, 'PanSou：网盘资源搜索工具'), 'shared');
    assert.equal(await share.shareToWeChat(pageUrl, 'PanSou：网盘资源搜索工具'), 'copied');
    assert.match(context.copied, /PanSou：网盘资源搜索工具\nhttps:\/\/panss\.dpdns\.org/);

    let prompted = '';
    const promptFallback = loadShare({ navigator: {}, prompt: (_, value) => { prompted = value; } });
    assert.equal(await promptFallback.share.shareToWeChat(pageUrl, 'PanSou：网盘资源搜索工具'), 'prompted');
    assert.match(prompted, /https:\/\/panss\.dpdns\.org/);
    console.log('share checks passed');
})();
