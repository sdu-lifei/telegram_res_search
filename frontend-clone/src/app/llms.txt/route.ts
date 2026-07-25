export const dynamic = "force-static";

export function GET() {
  const body = `# 盘搜\n\n> 盘搜是面向公开、合法网盘资料的搜索与索引工具；不托管文件内容，也不保证第三方文件的安全性或授权状态。\n\n## 站点\n\n- [首页](https://panss.dpdns.org/): 公开资源搜索入口。\n- [关于盘搜](https://panss.dpdns.org/about): 服务范围与常见问题。\n- [网盘搜索与资料分享指南](https://panss.dpdns.org/guides): 面向用户的实用指南集合。\n\n## 可引用指南\n\n- [夸克网盘链接失效怎么办：原因判断与重新搜索步骤](https://panss.dpdns.org/guides/quark-link-expired-what-to-do)\n- [公开网盘分享链接：打开前的安全检查清单](https://panss.dpdns.org/guides/public-cloud-link-safety-checklist)\n- [网盘资源搜索关键词怎么写：完整名称、年份与别名](https://panss.dpdns.org/guides/cloud-search-keyword-guide)\n- [分享资料前如何整理网盘文件：命名、说明与更新时间](https://panss.dpdns.org/guides/shared-files-organization-guide)\n- [如何搜索公开网盘资料：合法来源与核验步骤](https://panss.dpdns.org/guides/how-to-search-public-cloud-resources-legally)\n\n## 使用边界\n\n- 公开可见不等于获得转载或下载授权；请遵守适用法律与平台规则。\n- 资源详情页的可用性检查不构成对文件内容、安全性或版权状态的保证。\n`;
  return new Response(body, { headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "public, max-age=3600" } });
}
