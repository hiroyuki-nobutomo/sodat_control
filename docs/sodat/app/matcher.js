/* SODAT マッチングエンジン（ルールベース・プロトタイプ版）
   設計方針(docs/sodat-r8-architecture.md §6③):
   - 需給は同じタスク語彙(task_type_id)。既定は完全一致で結合。
   - 適性◎(初心者軽作業)のみ base で束ね、他作目の同ベース実績を割引加点。
   - 資格(qual_rules)は必須ゲート。対応可能時間の重なり・エリア一致はスコア加点。
   スコア = 完全一致実績*2 + 束ね加点(baseの他作目実績*1) + 空き5 + エリア3  （資格NGは除外） */
const Matcher = (() => {

  function overlapsAvailability(worker, req) {
    const rf = new Date(req.timing_from).getTime(), rt = new Date(req.timing_to).getTime();
    return worker.availability.some(a => {
      const af = new Date(a.available_from).getTime(), at = new Date(a.available_to).getTime();
      return af < rt && at > rf;               // 期間が少しでも重なる
    });
  }

  function match(req) {
    const t = SODAT.task(req.task_type_id);
    const farm = SODAT.farm(req.farm_id);
    const bundle = t.spot_aptitude === '◎';     // ◎ のみ束ねる
    // 資格ゲートは task_types の required_qual（危険作業区分に接地）を優先
    const requiredQual = t.required_qual || SODAT.db.qual_rules[t.base] || null;

    const rows = SODAT.db.workers.map(w => {
      const exact = SODAT.skillOf(w, req.task_type_id);
      const baseMap = SODAT.skillsByBase(w);
      const baseCnt = (baseMap[t.base] || {}).work_count || 0;
      const bundleBonus = bundle ? Math.max(0, baseCnt - exact) : 0;

      const qualPass = !requiredQual || w.qualifications.includes(requiredQual);
      const avail = overlapsAvailability(w, req);
      const areaMatch = w.area === farm.area;

      // 候補資格: 完全一致がある、または(◎かつ同ベース実績がある)。専門(−等)は完全一致必須。
      const hasSkill = exact > 0 || (bundle && baseCnt > 0);
      const eligible = qualPass && hasSkill;

      const score = eligible
        ? exact * 2 + bundleBonus * 1 + (avail ? 5 : 0) + (areaMatch ? 3 : 0)
        : 0;

      return {
        worker: w, exact, baseCnt, bundleBonus,
        qualPass, requiredQual, avail, areaMatch, eligible, score,
        reason: !qualPass ? `資格不足(${requiredQual})`
              : !hasSkill ? (bundle ? '該当スキルなし' : '専門タスク:実績なし')
              : null
      };
    });

    const eligible = rows.filter(r => r.eligible).sort((a, b) => b.score - a.score);
    const rejected = rows.filter(r => !r.eligible);
    return { req, task: t, farm, bundle, requiredQual, eligible, rejected };
  }

  // ② タスク提案: cultivation_observations × proposal_rules
  function proposalsForFarm(fid) {
    return SODAT.db.cultivation_observations
      .filter(o => o.farm_id === fid)
      .map(o => {
        const key = `${o.crop}|${o.growth_stage}`;
        const ttid = SODAT.db.proposal_rules[key];
        if (!ttid) return null;
        const t = SODAT.task(ttid);
        return { observation: o, task: t,
                 aptitude: t.spot_aptitude,
                 note: `${o.growth_stage} を検知 → ${t.task_name} を提案` };
      })
      .filter(Boolean);
  }

  return { match, proposalsForFarm };
})();
