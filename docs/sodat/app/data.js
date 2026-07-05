/* SODAT プロトタイプ データ層
   ダミー先行: fixtures.json を読むだけ。将来 Supabase に差し替える場合も
   このファイルの load() / getters を置き換えれば UI 側は無改修で済む。 */
const SODAT = (() => {
  let db = null;
  const byId = {};

  async function load() {
    if (db) return db;
    const res = await fetch('./fixtures.json', { cache: 'no-store' });
    db = await res.json();
    db.task_types.forEach(t => byId[t.task_type_id] = t);
    // 作業者UIでのローカル追記（work_records）を保持する簡易ストア
    db._local_work = JSON.parse(localStorage.getItem('sodat_local_work') || '[]');
    applyLocalWork();
    return db;
  }

  // ローカル追記の実績を worker.skills に反映（① スキル導出の簡易版）
  function applyLocalWork() {
    db._local_work.forEach(rec => {
      const w = db.workers.find(x => x.worker_id === rec.worker_id);
      if (!w) return;
      let s = w.skills.find(s => s.task_type_id === rec.task_type_id);
      if (!s) { s = { task_type_id: rec.task_type_id, work_count: 0, last_worked_at: rec.event_time }; w.skills.push(s); }
      s.work_count += rec.count || 1;
      s.last_worked_at = rec.event_time;
    });
  }

  function addWork(worker_id, task_type_id, count) {
    const rec = { worker_id, task_type_id, count: count || 1, event_time: db.demo_today + 'T09:00:00', source: 'worker_ui' };
    db._local_work.push(rec);
    localStorage.setItem('sodat_local_work', JSON.stringify(db._local_work));
    // 反映
    const w = db.workers.find(x => x.worker_id === worker_id);
    let s = w.skills.find(s => s.task_type_id === task_type_id);
    if (!s) { s = { task_type_id, work_count: 0, last_worked_at: rec.event_time }; w.skills.push(s); }
    s.work_count += rec.count; s.last_worked_at = rec.event_time;
    return rec;
  }
  function resetLocal(){ localStorage.removeItem('sodat_local_work'); location.reload(); }

  // getters
  const task = id => byId[id];
  const tasksByCrop = crop => db.task_types.filter(t => t.crop === crop);
  const farm = id => db.farms.find(f => f.farm_id === id);
  const worker = id => db.workers.find(w => w.worker_id === id);
  const requestsForFarm = fid => db.task_requests.filter(r => r.farm_id === fid);
  const allRequests = () => db.task_requests;

  // ワーカーの base 別実績合算（束ね用）
  function skillsByBase(w) {
    const m = {};
    w.skills.forEach(s => {
      const t = byId[s.task_type_id]; if (!t) return;
      m[t.base] = m[t.base] || { base: t.base, work_count: 0, crops: new Set() };
      m[t.base].work_count += s.work_count; m[t.base].crops.add(t.crop);
    });
    return m;
  }
  const skillOf = (w, taskId) => (w.skills.find(s => s.task_type_id === taskId) || {}).work_count || 0;

  return { load, get db(){return db;}, task, tasksByCrop, farm, worker,
           requestsForFarm, allRequests, skillsByBase, skillOf, addWork, resetLocal };
})();
