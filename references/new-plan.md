# 新 SPU 进池与建计划

## 1. 筛选

- 不在池（全站营销计划列表里没有这个 SPU）。
- 30 天销量 ≥ 5 单。
- 全域投后毛利率 ≥ 20%（履约毛利 − 折后广告消耗，再除以成交金额）。
- 累计评价数 ≥ 20，且有带图评价（平台拿不到带图评价条数时，用“累计评价≥20 且不在无带图评价名单”代替）。

## 2. 方法 A：批量模板（最稳）

用 jzt_ad_batch_new 生成 xlsx，在后台“全站营销-单品推广 → 批量操作”上传。
每行：广告主PIN、SPUID、操作场景=新建、产品线=全站营销-单品推广、预算、出价、SKU黑名单。
上传后回读预算、目标投产比、状态。

## 3. 方法 B：页面会话直接建（全自动）

代投 API 建单品推广会返回“无投放权限”，必须用浏览器页面会话。

### 3.1 准备

1. 用 Chrome 打开远程调试端口：
   chrome.exe --remote-debugging-port=9222 --user-data-dir=<临时目录> https://osw.jd.com/
2. 让用户在窗口里登录 ERP，按“京喜 → 推广 → 全站营销”进入页面。
3. 页面地址应为 cxjzt.jd.com/swa/index.html#/promote?currTab=Single。

### 3.2 关键令牌

- exposureAdoptsAssociationId：页面 sessionStorage 的 <pin>_600000004_sid。
- bidSuggestTraceId：POST /dspad/bidding/suggest 返回的 ext.traceId。
缺任一个都会返回“无投放权限”。

### 3.3 单个计划请求

POST https://cxjzt-api.jd.com/swa/campaign/add

{
  "exposureAdoptsAssociationId": "<sessionStorage 里的值>",
  "abExperimentalIdentification": "",
  "campaignType": 101,
  "swaCampaignCreateCommandList": [{
    "campaignType": 101,
    "biddingType": 8192,
    "biddingPrice": "3.0",
    "biddingTarget": 22,
    "biddingControlType": 2,
    "dayBudget": "100",
    "adDto": { ...spuDetailList 原样行，补 skuIdList/sxuType/sxuId/isSpu/sourceType/biddingSelectType... },
    "location": "swaBudgetSuggest",
    "sureWinOpen": 0,
    "strategyIdList": [],
    "strategyVersionId": "",
    "speedUpSetting": null
  }],
  "bidSuggestTraceId": "<suggest 返回的 traceId>",
  "spuRecommendTraceId": "",
  "recProductRequestFrom": "swaSelection",
  "campaignCouponStatus": 1,
  "requestFrom": 0
}

adDto 从 POST /dspad/common/spu/info {spuIds:[spu]} 的 spuDetailList[0] 取，SKU 列表在 longListMap[spu]。
dayBudget 传字符串；要“不限”传空字符串。

### 3.4 批量

- 先建 1 个，回读确认预算、目标投产比、状态。
- 再按 50 个一批循环，每个之间停 0.3~0.5 秒。
- 结果记下 campaignId，最后统一回读。

### 3.5 回读

页面会话 POST /swa/ad/list，obys=createdTime|desc，pageSize=500，按 spuId 匹配。
核对：dayBudget、groupBid（目标投产比）、status=2。

### 3.6 黑名单

新建时 adDto 里的 blackSkuList 不生效。建完后逐计划：
POST /swa/skublack/update {campaignId, adGroupId, skuIds:[...], requestFrom:0}
再 POST /swa/skublack/query 回读比对。

## 4. 注意

- 平台一品一计划有数量上限（当前口径最多 200 个左右），加到上限会报错，按成交额优先。
- 新品计划（campaignType=117）只能建“新品范围”内的 SPU，不要拿它替代单品推广。
- 代投 API 的 campaign/get 可能查不到页面会话刚建的计划，以页面会话为准。
