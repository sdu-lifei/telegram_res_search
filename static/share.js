(function (root) {
    function buildShareUrl(platform, url, text) {
        if (platform === "x") {
            return `https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}&url=${encodeURIComponent(url)}`;
        }
        if (platform === "whatsapp") {
            return `https://api.whatsapp.com/send?text=${encodeURIComponent(`${text}\n${url}`)}`;
        }
        throw new Error(`Unsupported share platform: ${platform}`);
    }

    function buildPublicUrl(locationLike, keyword) {
        const url = new URL(locationLike.href);
        if (keyword) url.searchParams.set("kw", keyword);
        else url.searchParams.delete("kw");
        url.hash = "";
        return url.toString();
    }

    function shareText(title, keyword) {
        if (!title) return "PanSou：网盘资源搜索工具";
        return `PanSou 搜索结果：${title}${keyword ? `，查询：${keyword}` : ""}`;
    }

    async function shareToWeChat(url, text) {
        const shareData = { title: "PanSou", text, url };
        if (typeof navigator.share === "function") {
            try {
                await navigator.share(shareData);
                return "shared";
            } catch (error) {
                if (error && error.name === "AbortError") return "cancelled";
            }
        }

        const content = `${text}\n${url}`;
        if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
            try {
                await navigator.clipboard.writeText(content);
                return "copied";
            } catch (_) {
                // Fall through to a user-visible copy prompt.
            }
        }
        root.prompt("请复制以下内容，再分享到微信群：", content);
        return "prompted";
    }

    const api = { buildShareUrl, buildPublicUrl, shareText, shareToWeChat };
    if (typeof module !== "undefined" && module.exports) module.exports = api;
    else root.PanSouShare = api;
})(typeof window !== "undefined" ? window : globalThis);
