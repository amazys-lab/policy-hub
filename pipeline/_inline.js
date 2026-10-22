
// ==== 全局错误捕获 ====
window.onerror=function(msg,src,line,col,err){
  var b=document.getElementById('__errbar');
  if(!b){b=document.createElement('div');b.id='__errbar';b.style.cssText='position:fixed;left:0;top:0;right:0;z-index:99999;background:#C0392B;color:#fff;padding:10px 14px;font-size:13px;line-height:1.6;max-height:45vh;overflow:auto;';(document.body||document.documentElement).appendChild(b);}
  b.innerHTML='⚠️ 页面脚本报错（截图发我）：<br>'+String(msg)+'<br>行号 '+(line||'?')+' 列 '+(col||'?')+(err&&err.stack?'<pre style="margin:6px 0 0;font-size:11px;white-space:pre-wrap;">'+err.stack+'</pre>':'');
};
// ==== API 版：页面不内嵌政策数据，全部实时从后端匹配接口取 ====
const DATA=[]; const HK=[]; const OS=[];
const EMPWIN={windows:[],count:0,hotline:"",source:"",area_rule:{}}; const HKWIN={windows:[]};
const API_BASE=(function(){try{const _sv=localStorage.getItem("sz_api_base");if(_sv)return _sv;}catch(e){}
 const _h=location.hostname||"";
 if(location.protocol.indexOf("http")===0&&_h&&_h!=="127.0.0.1"&&_h!=="localhost")return ""; // 云端：同源相对路径，自动走HTTPS、无跨域
 return "http://127.0.0.1:8000"; // 本地双击file://或本机开发：连本机8000
})();
let DATA_VERSION="";
// 城市名静态兜底（后端未启动/双击打开时使用）；运行时以 /meta 返回的 cities 为准，新城市发版后自动出现、无需改前端
let CITY_NAMES={};   // 运行时由 /meta 的 cities 回填（本仓不预置城市数据）
let _CITY_FIELDS_TPL=null;   // 字段池克隆模板（不写进 CITY_FIELDS，避免污染城市遍历）
function fillCitySelect(cities,preserve){
  const sel=document.getElementById("citySelect");if(!sel||!cities||!cities.length)return;
  const cur=preserve?sel.value:"";
  cities.forEach(c=>{if(c&&c.code&&CITY_NAMES[c.code]===undefined)CITY_NAMES[c.code]=c.name;});
  sel.innerHTML=cities.map(c=>'<option value="'+c.code+'"'+(c.code===cur?" selected":"")+'>'+c.name+"</option>").join("");
  if(!Array.from(sel.options).some(o=>o.value===cur))sel.value=cities[0].code;
  // ★ CITY_FIELDS 默认是空表（本仓不带城市数据）：任何新出现的城市码都克隆 FIELD_TPL，
  //   否则 cityDoms() 取到 undefined ⇒ 各分节被误判成「本市无此域」而收起。
  if(typeof CITY_FIELDS!=="undefined"&&typeof FIELD_TPL!=="undefined"){
    if(!_CITY_FIELDS_TPL)_CITY_FIELDS_TPL=JSON.parse(JSON.stringify(FIELD_TPL));
    cities.forEach(c=>{if(c&&c.code&&!CITY_FIELDS[c.code])CITY_FIELDS[c.code]=JSON.parse(JSON.stringify(_CITY_FIELDS_TPL));});
  }
}
async function apiMatch(profile){
  const res=await fetch(API_BASE+"/api/v1/match",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({profile})});
  if(!res.ok)throw new Error("HTTP "+res.status);
  const j=await res.json(); DATA_VERSION=j.data_version; return j;
}
(async function(){try{const m=await(await fetch(API_BASE+"/api/v1/meta")).json();DATA_VERSION=m.data_version;if(m.cities)fillCitySelect(m.cities,true);
 const dl=Object.keys(m.domains||{}).map(k=>(m.domains[k].label||k)+m.domains[k].count).join("·");const st=document.getElementById("stat");if(st)st.textContent="已连接匹配服务 "+API_BASE+"　数据版本 "+m.data_version+"（"+dl+"）";}catch(e){const st=document.getElementById("stat");if(st)st.innerHTML='<span style="color:#c00">未连接后端 '+API_BASE+'，请先运行 python -m uvicorn server.app:app --port 8000</span>';}})();
// 就业窗口：按区分组渲染（同一数据只存一份，多卡复用）
function empWinGroupsHtml(){
  const groups={};EMPWIN.windows.forEach(w=>{(groups[w.district]=groups[w.district]||[]).push(w);});
  return Object.keys(groups).map(d=>'<div style="margin-top:6px;"><b>'+esc(d)+'（'+groups[d].length+'个）</b>'+groups[d].map(w=>'<div class="mat">'+esc(w.level+"｜"+w.name+"｜"+w.addr+"｜电话 "+w.tel+"｜"+w.time)+'</div>').join("")+'</div>').join("");
}
function empWinDetailsHtml(kind){
  const rule=(EMPWIN.area_rule&&EMPWIN.area_rule[kind])||"按单位注册地/本人就业地选所在区或街道";
  return '<details><summary>全市经办窗口（地址·电话，按'+esc(rule)+'选，共 '+EMPWIN.count+' 个）</summary><div class="inner"><div class="mat" style="color:#6B7280;">'+esc(EMPWIN.hotline)+'；来源：'+esc(EMPWIN.source)+'</div>'+empWinGroupsHtml()+'</div></details>';
}

// 画像字段元数据(key -> 文案/类型)，与规则字段一一对应
/*WB-EXTRA2*/
const FORM = {
  person:{
    tags:{title:"② 你的身份(可多选)",options:[
      ["grad_2y","毕业2年内高校毕业生"],["graduating_hardship","毕业学年困难学生(低保/残疾/脱贫/助学贷款)"],
      ["student_in_school","本市在校普通高校学生"],["employ_difficult","已认定就业困难人员"],["key_group","重点群体（脱贫人口/登记失业半年以上/零就业低保/返乡农民工等）"],["graduates","高校毕业生（含应届/毕业学年）"],["hk_macao_youth","港澳台居民（含台湾地区居民）"],["registered_unemployed","登记失业人员"],["registered_unemployed_6m","登记失业半年以上人员"],["poverty_pop","脱贫人口/防止返贫监测对象"],["returned_migrant","返乡入乡农民工"],["zero_employment_family","零就业家庭成员"],["low_income_family","低保家庭成员"],["grad_year","毕业年度高校毕业生"],["prisoner_released","刑满释放人员"]]},
    tags2:{field:"ent_types",title:"④ 机构类型（仅在你是培训机构/用人单位时选；个人求职者不用选）",options:[["small_micro","小微企业"],["social_org","社会组织"],["housekeeping_emp","员工制家政企业"],["housekeeping_gen","一般家政企业"],["incubator","创业孵化基地"],["vocational","院校(高校/中职/技工)"],["hr_agency","经营性人力资源服务机构"],["train_inst","定点培训机构/院校"],["general","一般用人单位"]]},
    nums:[["personal_ss_months","以个人身份连续缴社保(月)"],["weekly_hours","每周累计工作(小时)"],
      ["age","本人年龄(岁)"],["personal_ss_monthly_amount","个人社保月缴费额(元,缴费补贴测算用)"],
      ["contract_years","本人与单位签订劳动合同年限(年,基层/中小微就业补贴要求≥1)"],
      ["gz_work_days","本市:纳税年度工作累计天数(须>90)"],["zh_work_days","本市:纳税年度工作累计天数(须>90)"],
      ["fs_work_days","本市:纳税年度工作累计天数(须>90)"],["hz_work_days","本市:纳税年度工作累计天数(须>90)"],
      ["dg_work_days","本市:纳税年度工作累计天数(须>90)"],["zs_work_days","本市:纳税年度工作累计天数(须>90)"],
      ["jm_work_days","本市:纳税年度工作累计天数(须>90)"],["zq_work_days","本市:纳税年度工作累计天数(须>90)"],
      ["gz_taxable_income","本市紧缺人才:纳税年度应纳税所得额(万元,须≥30)"],
      ["ui_paid_months","足额缴失业保险费(月)"]],
    bools:[["is_sz_student","本市普通高校/本市生源院校学生"],["works_at_smb","在中小微企业/个体/社会组织/社区岗位就业"],
      ["has_training_cert","参加目录内职业技能培训并取得证书（可领技能培训补贴）"],["is_flexible_job","从事规定的灵活就业岗位"],
      ["in_gba_youth_plan","参加港澳特区政府大湾区青年就业计划并在本市就业"],
      ["registered_flex_job","已以灵活就业类型办理就业登记"],["flex_pay_employee_ss","以灵活就业身份参加企业职工养老/医疗保险并缴费"],
      ["is_individual_business","已办理个体工商户登记并经营"],["self_keygroup_or_vet","本人属重点群体(脱贫/失业半年/零就业低保/毕业年度)或自主就业退役士兵"],
      ["other_loan_clean","除助学/房贷/车贷/扶贫贷外无其他商业银行贷款"],["work_at_housekeeping_emp","到员工制家政企业就业"],
      ["registered_local","已在本市办理就业登记/登记注册并有具体经营项目"],["no_credit_violation","信用良好、非失信被执行人、无严重不良信用记录"],
      ["founder_training_selected","经选拔参加初创企业经营者能力提升培训并完成"],
      ["is_high_end_talent","经认定的境外高端人才"],["is_scarce_talent","符合境外紧缺人才目录"],
      ["in_key_industry","在科技创新/重点发展产业领域工作"],["no_crime_3y","申请前3年无刑事处罚、非严重失信"],
      ["pay_iit_gz","在本市依法缴纳个税"],["pay_iit_zh","在本市依法缴纳个税"],
      ["pay_iit_fs","在本市依法缴纳个税"],["pay_iit_hz","在本市依法缴纳个税"],
      ["pay_iit_dg","在本市依法缴纳个税"],["pay_iit_zs","在本市依法缴纳个税"],
      ["pay_iit_jm","在本市依法缴纳个税"],["pay_iit_zq","在本市依法缴纳个税"],
      ["has_worker_skill_cert","组织职工取得目录内职业技能等级证书"],
      ["run_training_class","举办规定创业培训班次且学员考核合格"],
      ["normal_operation","登记满12个月、申请前6个月正常经营且未列入经营异常名录"],
      ["is_legal_rep","申请人为登记3年内初创企业法定代表人/经营者(创业带动用)"]]
  },
  entrepreneur:{
    tags:{title:"② 创业者身份(至少符合一项)",options:[
      ["grad_5y","毕业5年内/留学回国人员"],["grad_2y","毕业2年内高校毕业生"],["veteran","复员转业退役军人"],["employ_difficult","登记失业人员"],
      ["hk_macao_youth","港澳台居民"],["shenzhen_huji","本地户籍"],["key_group","重点群体（脱贫人口/登记失业半年以上/零就业低保/返乡农民工等）"],["graduates","高校毕业生（含应届/毕业学年）"],["registered_unemployed","登记失业人员"],["registered_unemployed_6m","登记失业半年以上人员"],["poverty_pop","脱贫人口/防止返贫监测对象"],["returned_migrant","返乡入乡农民工"],["zero_employment_family","零就业家庭成员"],["low_income_family","低保家庭成员"],["grad_year","毕业年度高校毕业生"],["prisoner_released","刑满释放人员"]]},
    nums:[["founder_ss_months","本人在初创企业缴社保(月)"],["biz_reg_months","企业商事登记至今(月)"],
      ["rent_months","实际缴纳租金(月)"],["hire_count","带动就业/招用人数(人)"],
      ["ent_ss_months","为招用员工缴社保(月)"],["contract_years","与员工劳动合同年限(年)"],
      ["age","本人年龄(岁)"],["rent_year_count","申领租金补贴的年数(年,最长3)"]],
    bools:[["is_legal_rep","本人是法定代表人/经营者"],["normal_operation","企业正常经营"],
      ["has_own_property","经营场地为自有物业(场租补贴要求非自有)"],["rent_addr_match","租赁地址与注册地址一致"],
      ["no_credit_violation","无拖欠工资/欠缴社保等严重失信记录"],["won_city_competition","在全市性创业大赛获奖并在本市完成商事登记"],
      ["is_individual_business","已办理个体工商户登记并经营"],["self_keygroup_or_vet","本人属重点群体(脱贫/失业半年/零就业低保/毕业年度)或自主就业退役士兵"],
      ["registered_local","已在本市登记注册且有具体经营项目"],["other_loan_clean","除助学/房贷/车贷/扶贫贷外无其他商业银行贷款"],
      ["founder_training_selected","经选拔参加初创企业经营者能力提升培训并完成"],
      ["has_training_cert","参加创业培训并取得创业培训(实训)合格证书"],
      ["run_training_class","举办规定创业培训班次(GYB/SYB等)且学员考核合格"]]
  },
  /* ⚠️ 死配置说明（2026-10-08 标注，对应 10-项目巡检 P2-5）：
     renderForm() 只对 person / entrepreneur 调用（见 SUBJECT 分支），
     unit 的控件由静态 HTML #entBox + 外部控件注入负责渲染 —— 本块不会被渲染成控件。
     但本块仍被当作 unit 画像的标签字典使用：tagLabel() 与画像摘要都查 FORM[p.kind].tags/nums/bools，
     所以不要删；改字段文案请改这里。
     静态分析/测试若把本块当【可渲染控件】，会算少缺口（P2-5 踩过）。 */
  unit:{
    tags:{title:"② 单位类型(可多选)",field:"ent_types",options:[
      ["small_micro","小微企业"],["social_org","社会组织"],["housekeeping_emp","员工制家政企业"],
      ["housekeeping_gen","一般家政企业"],["incubator","创业孵化基地"],["vocational","院校(高校/中职/技工)"],
      ["hr_agency","经营性人力资源服务机构"],["train_inst","定点培训机构/院校"],["general","一般用人单位"]]},
    radio:[["ent_scale","③ 企业规模划型(稳岗返还用,不确定可不选)",[["smb","中小微企业"],["large","大型企业"]]]],
    nums:[["ent_ss_months","为招用人员连续缴社保(月)"],["contract_years","劳动合同年限(年)"],
      ["hire_grad2y_count","招用毕业2年内毕业生(人)"],["hire_employdiff_count","招用就业困难等人员(人)"],
      ["hire_veteran_within1y_count","招用退役1年内退役军人(人)"],["hire_poverty_count","招用脱贫/防止返贫人口(人)"],
      ["hire_trainee_count","就业见习人数(人)"],["unemp_insurance_heads","家政从业人员失业保险缴费(人)"],
      ["hire_unemp6m_count","招用登记失业半年以上人员(人)"],["hkmo_intern_months","接收港澳台青年实习(月)"],
      ["incubated_success_count","孵化成功团队(户)"],
      ["staff_count","在职职工总数(人,残保金/比例用)"],["ui_paid_months","足额缴失业保险费(月)"],
      ["ui_premium_lastyear","上年实缴失业保险费(元,稳岗测算用)"],
      ["hire_veteran_count","招用自主就业退役士兵(人,税收用,不限退役1年内)"],
      ["hire_keygroup_count","招用重点群体(脱贫/失业半年/零就业低保,人,税收用)"],
      ["public_welfare_heads","公益性岗位在岗人数(人)"],["jiazheng_avg_pay_heads","家政月均参保人数(人)"],
      ["student_eval_count","院校学生取得证书人数(人)"],["job_intro_count","成功介绍就业人数(人)"],
      ["monitor_worker_count","承担就业监测工作人员(人)"],["apprentice_count","完成学徒制培训人数(人)"],
      ["mom_post_count","在岗灵活就业岗员工人数(人)"],
      ["hire_count","招用员工总人数(人,不含法人本人;创业带动/学徒制用)"],
      ["rd_expense","上年度研发费用支出(元,研发加计/资助用)"],
      ["hire_new_nonlocal_count","新招用非本地户籍员工人数(人,本市)"]],
    bools:[["is_labor_dispatch","属于劳务派遣单位(多数补贴除外)"],["has_public_welfare_post","已开发经认定的公益性岗位"],
      ["has_grassroots_post","已开发基层公共就业岗位"],["free_skill_eval","为本校在校生免费提供技能评价"],
      ["has_student_mid_cert","有学生取得中级工以上证书"],["incubate_over_1y","为入孵团队提供1年以上孵化"],
      ["bought_commercial_insurance","已出资购买家政商业保险"],["trainee_ratio_ok","见习人数≤在职职工10%"],
      ["bought_intern_insurance","已为见习人员购意外险/工伤险"],
      ["no_credit_violation","无拖欠工资/欠缴社保等严重失信记录"],["has_worker_skill_cert","组织职工取得目录内职业技能等级证书"],
      ["run_apprentice_program","开展企业新型学徒制培训并完成全部培训评价"],["hkmo_intern","接收港澳台青年连续实习满1个月以上"],
      ["not_zombie","非僵尸企业/未严重失信/符合产业环保政策"],["no_layoff","上年度未裁员"],
      ["layoff_rate_ok","上年度裁员率符合控制目标上限"],["is_employment_monitor_point","被认定为就业失业监测点并按时报送"],
      ["mom_post_base_certified","获评省级灵活就业岗就业基地"],["nanyue_jiazheng_registered","企业及员工已在南粤家政平台上岗登记"],
      ["disabled_ratio_below_quota","安排残疾人就业未达规定比例"],["hire_keygroup_ratio_ok","新招重点群体占在职职工比例达标(小微贷条件)"],
      ["pay_trainee_80pct","按不低于当地最低工资80%发见习补贴"],["run_training_class","举办规定创业培训班次且学员考核合格"],
      ["has_training_cert","组织员工参加职业技能培训并取得职业资格/技能等级/合格证书"],
      ["is_legal_rep","申请人为登记3年内初创企业法定代表人/经营者(创业带动用)"],
      ["normal_operation","登记满12个月、申请前6个月正常经营且未列入经营异常名录"],
      ["founder_training_selected","经营者经选拔参加初创企业经营者能力提升培训并完成"],
      ["is_small_low_profit","符合小型微利企业条件(年应纳税所得额≤300万/从业≤300人/资产≤5000万)"],
      ["is_vat_small_scale","增值税小规模纳税人(年应税销售额未超标)"],
      ["is_hnte","持有有效期内国家高新技术企业证书"],
      ["is_sme_tech","已入库科技型中小企业(当年取得登记编号)"],
      ["hnte_certified","本年度通过高企认定(首次/重新，对应认定资助)"],
      ["hire_elig_ratio_ok","招用符合条件人员比例达标(本市)"],
      ["no_wage_ss_arrears","无拖欠工资、欠缴社保记录(本市)"]]
  }
};
let kind="person", selTags=new Set(), selTags2=new Set();

function renderForm(){
  const cfg=FORM[kind], area=document.getElementById("formarea");
  const _cv=document.getElementById("citySelect").value;
  const _cfinfo=(typeof CITY_FIELDS!=="undefined")?CITY_FIELDS[_cv]:null;
  const _FF=(_cfinfo&&_cfinfo.fields[kind])?new Set(_cfinfo.fields[kind]):null;
  const _keep=f=>!_FF||_FF.has(f);
  selTags=new Set(); selTags2=new Set();
  let h='<h2>'+cfg.tags.title+'</h2><div class="chiprow">';
  cfg.tags.options.filter(o=>_keep(cfg.tags.field||"identities")).forEach(o=>{h+='<div class="chip" data-v="'+o[0]+'">'+o[1]+'</div>';});
  h+='</div>';
  if(cfg.tags2){h+='<h2>'+cfg.tags2.title+'</h2><div class="chiprow">';
    cfg.tags2.options.filter(o=>_keep(cfg.tags2.field)).forEach(o=>{h+='<div class="chip" data-g="2" data-v="'+o[0]+'">'+o[1]+'</div>';});
    h+='</div>';}
  h+='<h2>'+(cfg.radio?'④ 具体情况':'③ 具体情况')+'</h2><div class="grid2">';
  cfg.nums.filter(n=>_keep(n[0])).forEach(n=>{h+='<div class="fld"><label>'+n[1]+'</label><input type="number" min="0" id="n_'+n[0]+'" value=""></div>';});
  (cfg.radio||[]).filter(r=>_keep(r[0])).forEach(r=>{h+='</div><h2>③ '+r[1].replace(/^[①②③④]\s*/,'')+'</h2><div class="chiprow">'+r[2].map(o=>'<label class="check"><input type="radio" name="r_'+r[0]+'" value="'+o[0]+'">'+o[1]+'</label>').join("")+'</div><div class="grid2">';});
  h+='</div><div style="margin-top:8px;">';
  cfg.bools.filter(b=>_keep(b[0])).forEach(b=>{h+='<label class="check"><input type="checkbox" id="b_'+b[0]+'">'+b[1]+'</label>';});
  h+='</div>';
  area.innerHTML=h;
  area.querySelectorAll(".chip").forEach(c=>c.onclick=()=>{
    const v=c.dataset.v, S=(c.dataset.g==="2")?selTags2:selTags;
    if(S.has(v)){S.delete(v);c.classList.remove("sel");}else{S.add(v);c.classList.add("sel");}
  });
}
// kindrow 已移除：申报主体由顶部 subjectSwitch 统一选择（见 initSubject）

function collect(){
  const cfg=FORM[kind], p={kind:kind};
  const tagField=cfg.tags.field||"identities"; p[tagField]=[...selTags];
  cfg.nums.forEach(n=>{const el=document.getElementById("n_"+n[0]);p[n[0]]=el&&el.value!==""?Number(el.value):0;});
  (cfg.radio||[]).forEach(r=>{const el=document.querySelector('input[name="r_'+r[0]+'"]:checked');p[r[0]]=el?el.value:"";});
  cfg.bools.forEach(b=>{const el=document.getElementById("b_"+b[0]);p[b[0]]=!!(el&&el.checked);});
  if(cfg.tags2)p[cfg.tags2.field]=[...selTags2];
  if(!p.identities)p.identities=[]; if(!p.ent_types)p.ent_types=[];
  return p;
}
function condOK(p,c){
  const a=p[c.f]!==undefined?p[c.f]:(Array.isArray(c.v)?[]:(typeof c.v==="boolean"?false:0));
  switch(c.op){
    case ">=":return a>=c.v; case "<=":return a<=c.v; case "==":return a===c.v;
    case "!=":return a!==c.v; case "intersects":return (a.filter(x=>c.v.includes(x))).length>0;
  } return false;
}
function evaluate(p,pol){
  // D2(2026-10-10)：overseas 是叠加身份 —— 海外/留学人才首先是个"人"，标 person 的政策同样应命中；
  // 反向不成立（选「个人」不吃 only-overseas）。与 policy_hub/engine/matcher.py 同源。
  const _ek=(p.kind==="overseas")?["overseas","person"]:[p.kind];
  if(!_ek.some(x=>pol.cond.applicant_kinds.includes(x)))return{st:"skip"};
  const t=pol.cond.any_identities;
  if(t&&t.length&&!t.some(x=>(p.identities||[]).includes(x)))return{st:"no"};
  const fails=pol.cond.must.filter(c=>!condOK(p,c)).map(c=>c.label);
  const am=pol.cond.any_must, total=pol.cond.must.length+(am?1:0);
  if(am&&!am.conds.some(c=>condOK(p,c)))fails.push(am.label);
  return{st:fails.length===0?"match":(fails.length<total?"near":"no"),fails};
}
// 金额测算：返回结果文本 + 分步明细 lines[[项,值]]，供卡片与清单共用
function estimate(p,am){
  const n=k=>Number(p[k]||0), money=v=>Math.round(v).toLocaleString();
  if(!am||!am.kind){return{kind:"none",val:0,txt:"按官方当年公布标准",lines:[["说明","金额以官方最新文件及窗口审核为准"]]};}
  if(am.kind==="once"){return{kind:am.kind,val:am.value,txt:am.value+" 元（一次性）",lines:[
    ["计发标准",(am.unit||(am.value+" 元"))+"，一次性发放"],
    ["测算金额",money(am.value)+" 元（一次性）"]]};}
  if(am.kind==="once_x_count"){const cnt=n(am.count_field),v=am.per*cnt;return{kind:am.kind,val:v,txt:"约 "+money(v)+" 元（"+am.per+" 元/人 × "+cnt+" 人，一次性）",lines:[
    ["计发标准",am.per+" 元/人，一次性"],
    ["符合条件人数",cnt+" 人（取自左侧画像填写，不足计发口径的人数按 0 计）"],
    ["测算式",am.per+" × "+cnt],
    ["参考金额","约 "+money(v)+" 元（一次性）"]]};}
  if(am.kind==="month_x_count"){const cnt=n(am.count_field),v=am.per*cnt;return{kind:am.kind,val:v,txt:"约 "+money(v)+" 元/月（"+am.per+" 元/人/月 × "+cnt+" 人），最长按政策期限",lines:[
    ["计发标准",am.per+" 元/人/月"],
    ["符合条件人数",cnt+" 人（取自画像）"],
    ["每月测算",am.per+" × "+cnt+" = "+money(v)+" 元/月"],
    ["发放期限","累计最长按政策规定期限，按月计发（未缴月份相应扣减）"]]};}
  if(am.kind==="tiered_hire"){const x=n(am.count_field),f=Math.min(x,am.first_n),r=Math.max(0,x-am.first_n),s1=f*am.first,s2=r*am.rest,v=Math.min(am.cap,s1+s2);return{kind:am.kind,val:v,txt:"约 "+money(v)+" 元（前"+am.first_n+"人各"+am.first+"元、第"+(am.first_n+1)+"人起各"+am.rest+"元，封顶"+money(am.cap)+"元）",lines:[
    ["招用总人数",x+" 人（取自画像）"],
    ["第一档：前"+am.first_n+"人",f+" 人 × "+am.first+" 元 = "+money(s1)+" 元"],
    ["第二档：第"+(am.first_n+1)+"人起",r+" 人 × "+am.rest+" 元 = "+money(s2)+" 元"],
    ["分档合计",money(s1+s2)+" 元"],
    ["封顶后参考额","封顶 "+money(am.cap)+" 元，取较小值 → 约 "+money(v)+" 元（一次性）"]]};}
  return{kind:am.kind,val:null,txt:am.text,lines:[["计发方式",am.text]]};
}
function esc(s){return String(s==null?"":s).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}
// ===== 落户通道（与 policy_hub/engine/matcher.py 同构）=====
function hkV(id,d){const el=document.getElementById(id);if(!el)return d;return el.value!==""?Number(el.value):d;}
function hkC(id){const el=document.getElementById(id);return !!(el&&el.checked);}
/*WB-EXTRA*/
const HK_EXTRA={};

function _hkExtraOf(){var e=document.getElementById("citySelect");return HK_EXTRA[e?e.value:""]||null;}
function renderHkExtra(){
  var box=document.getElementById("hkExtra"); if(!box)return;
  var ex=_hkExtraOf();
  if(!ex||(!Object.keys(ex.bools||{}).length&&!Object.keys(ex.nums||{}).length&&!Object.keys(ex.texts||{}).length&&!(ex.identities||[]).length)){box.innerHTML="";return;}
  var h='<div style="margin-top:10px;padding-top:8px;border-top:1px dashed #9EC5E8;">'
   +'<div style="font-size:12.5px;font-weight:600;color:#1F4E79;margin-bottom:2px;">📍 本市落户附加条件（选填；不同城市要求不同，按你所在地勾选）</div>'
   +'<div style="font-size:11.5px;color:#6B7280;margin-bottom:6px;">下列字段来自本市落户政策条件，填了才能判定该城各通道是否走得通。</div>';
  if((ex.identities||[]).length){
    h+='<div style="font-size:12.5px;color:#2D3748;margin:2px 0 4px;">我的情况（可多选）</div><div class="chiprow">';
    var IDL={college:"大专及以上学历",skill_talent:"职称/技能人才",fresh_grad:"应届毕业生",stable_residence:"稳定居住就业",family_reunion:"投靠亲属",talent:"高层次人才",other:"其他"};
    ex.identities.forEach(function(v){h+='<label class="check"><input type="checkbox" data-wbex="1" data-ff="hkident" data-val="'+v+'" id="hke_id_'+v+'">&nbsp;'+(IDL[v]||v)+'</label>';});
    h+='</div>';
  }
  var N=Object.keys(ex.nums||{}), B=Object.keys(ex.bools||{}), T=Object.keys(ex.texts||{});
  if(N.length){h+='<div class="grid2" style="margin-top:6px;">';
    N.forEach(function(f){h+='<div class="fld"><label>'+esc(ex.nums[f])+'</label><input type="number" min="0" id="hke_'+f+'" data-wbex="1"></div>';});
    h+='</div>';}
  if(T.length){h+='<div class="grid2" style="margin-top:6px;">';
    T.forEach(function(f){h+='<div class="fld"><label>'+esc(ex.texts[f])+'</label><input type="text" id="hke_'+f+'" data-wbex="1"></div>';});
    h+='</div>';}
  if(B.length){h+='<div style="margin-top:6px;">';
    B.forEach(function(f){h+='<label class="check"><input type="checkbox" id="hke_'+f+'" data-wbex="1">&nbsp;'+esc(ex.bools[f])+'</label>';});
    h+='</div>';}
  h+='</div>';
  box.innerHTML=h;
}
function _wbHkExtra(p){
  var ex=_hkExtraOf(); if(!ex)return p;
  Object.keys(ex.bools||{}).forEach(function(f){p[f]=hkC("hke_"+f);});
  Object.keys(ex.nums||{}).forEach(function(f){p[f]=hkV("hke_"+f,0);});
  Object.keys(ex.texts||{}).forEach(function(f){var e=document.getElementById("hke_"+f);p[f]=e?(e.value||""):"";});
  if((ex.identities||[]).length){p.identities=[].slice.call(document.querySelectorAll('#hkExtra input[data-ff="hkident"]:checked')).map(function(e){return e.dataset.val;});}
  return p;
}
function _wbHkExtraFilled(){
  var ex=_hkExtraOf(); if(!ex)return false;
  return [].slice.call(document.querySelectorAll("#hkExtra [data-wbex]")).some(function(e){
    return e.type==="checkbox"?e.checked:String(e.value||"").trim()!=="";});
}
function clearHkExtra(){
  [].slice.call(document.querySelectorAll("#hkExtra [data-wbex]")).forEach(function(e){
    if(e.type==="checkbox")e.checked=false;else e.value="";});
}
function _wbExCtl(scope){
  return [].slice.call(document.querySelectorAll("#"+scope+" [data-wbex]")).some(function(e){
    return e.type==="checkbox"?e.checked:String(e.value||"").trim()!=="";});
}

function collectHk(){
  const ownY=hkV("hk_ownyears",0),rentY=hkV("hk_rentyears",0),pmY=hkV("hk_pmyears",0),age=hkV("hk_age",0);
  const p={age:age,gender:(document.getElementById("hk_gender")||{}).value||"M",
    education_level:hkV("hk_edu",0),is_full_time:hkC("hk_fulltime"),grad_years:hkV("hk_gradyears",0),
    never_received:hkC("hk_neverrecv"),title_level:hkV("hk_title",0),skill_level:hkV("hk_skill",0),
    ss_years:hkV("hk_ssyears",0),in_shortage_catalog:hkC("hk_shortage"),has_skill_award:hkC("hk_award"),
    healthy:hkC("hk_healthy"),no_crime:hkC("hk_nocrime"),has_sz_social_insurance:hkC("hk_ss"),
    has_residence_permit:hkC("hk_permit"),still_paying_ss:hkC("hk_still"),
    housing_own_years:ownY,housing_rent_years:rentY,housing_own_months:ownY*12,housing_rent_months:rentY*12,
    pension_or_medical_years:pmY,ss_months:pmY*12,ss_kinds_count:hkV("hk_kinds",0),
    has_overseas_qualification:hkC("hk_osq"),overseas_degree:hkC("hk_osdeg"),visiting_scholar_1y:hkC("hk_visit"),
    tax_legal_3y:hkV("hk_taxlegal",0),tax_shareholder_3y:hkV("hk_taxshare",0),tax_iit_3y:hkV("hk_taxiit",0),tax_individual_3y:hkV("hk_taxind",0),
    same_enterprise_3y:hkC("hk_sameent"),family_relation:((document.getElementById("hk_rel")||{}).value||""),
    has_sz_family_huji:hkC("hk_szfam"),spouse_separate_years:hkV("hk_spyears",0),sz_huji_years:hkV("hk_szyears",0),has_special_policy_case:hkC("hk_special"),special_kind:((document.getElementById("hk_specialkind")||{}).value||"")};
  _wbHkExtra(p);
  const has=age>0||hkV("hk_edu",0)>0||hkV("hk_gradyears",0)>0||ownY>0||rentY>0||pmY>0
    ||hkV("hk_taxlegal",0)>0||hkV("hk_taxshare",0)>0||hkV("hk_taxiit",0)>0||hkV("hk_taxind",0)>0
    ||hkV("hk_spyears",0)>0||hkV("hk_szyears",0)>0||((document.getElementById("hk_rel")||{}).value||"")!==""
    ||hkC("hk_fulltime")||hkC("hk_ss")||hkC("hk_permit")||hkC("hk_neverrecv")||hkC("hk_shortage")||hkC("hk_award")
    ||hkC("hk_osq")||hkC("hk_osdeg")||hkC("hk_visit")||hkC("hk_sameent")||hkC("hk_szfam")||hkC("hk_special")
    ||_wbHkExtraFilled();
  return {p:p,has:has};
}
function hkFails(p,must){return (must||[]).filter(c=>!condOK(p,c)).map(c=>c.label);}
function hkPoints(p,sr){
  const own=Number(p[sr.own_field]||0),rent=Number(p[sr.rent_field]||0);
  const housing=Math.max(own*sr.own_per_month,rent*sr.rent_per_month);
  const ss=Number(p[sr.ss_months_field]||0)*sr.ss_per_kind_month*Number(p[sr.ss_kinds_field]||0);
  return Math.round((housing+ss)*10)/10;
}
function channelDecide(p,ch){
  const out={id:ch.id,name:ch.name,channel_type:ch.channel_type,status:"no",missing:[],branch_hit:null,score:null};
  const cond=ch.cond;if(!cond){out.status="to_collect";return out;}
  const bm=hkFails(p,cond.base_must);if(bm.length){out.missing=bm;return out;}
  if(cond.branches&&cond.branches.length){
    let hit=null,best=null;
    cond.branches.forEach(br=>{const m=hkFails(p,br.must);if(!m.length&&!hit)hit=br.name;if(!best||m.length<best.length)best=m;});
    if(!hit){out.missing=best||[];out.status="near";return out;}
    out.branch_hit=hit;
  }
  if(cond.score_rule)out.score=hkPoints(p,cond.score_rule);
  out.status="eligible";return out;
}
function hkCard(ch,d){
  const ok=d.status==="eligible";
  let badge=ok?'<span class="badge b-ok">可走此通道</span>':'<span class="badge b-warn">暂不满足·差条件</span>';
  if(ok&&ch.channel_type==="competition")badge+='<span class="badge b-warn">排序竞争·不承诺结果</span>';
  let extra="";
  if(ok&&d.branch_hit)extra+='<div class="kv">命中路径：'+esc(d.branch_hit)+'</div>';
  if(ok&&d.score!=null)extra+='<div class="hkscore">预估积分：约 '+d.score+' 分（规则估算，最终以当年公告与排序为准）</div>';
  if(!ok)extra+='<div class="miss">还需满足：'+d.missing.map(esc).join('；')+'</div>';
  extra+='<div class="hktag">'+esc(ch.promise||"")+'</div>';
  extra+='<div class="kv"><b>政策原文：</b>'+(ch.guide_url?'<a href="'+ch.guide_url+'" target="_blank" rel="noopener" style="color:#1A5FB4;word-break:break-all;">查看原文</a>':"")+'　依据：'+esc(ch.source_doc||"")+'</div>';
  if(ch.special_cases&&ch.special_cases.length)extra+='<details open><summary>特殊情形与受理部门（'+ch.special_cases.length+'类）</summary><div class="inner">'+ch.special_cases.map(s=>'<div class="kv"><b>'+esc(s.case)+'：</b>'+esc(s.dept)+'</div>').join("")+'</div></details>';
  if(ch.click_steps&&ch.click_steps.length)extra+='<details><summary>操作路径（分步点击·电脑端）</summary><div class="inner"><ol style="margin:4px 0 0 18px;padding:0;">'+ch.click_steps.map(s=>'<li style="margin-bottom:3px;">'+esc(s)+'</li>').join("")+'</ol></div></details>';
  if(ch.deadline)extra+='<details><summary>⏰ 截止/时效规则（申报窗口·办理时限）</summary><div class="inner">'+esc(dlText(ch))+'</div></details>';
  return '<div class="card '+(ok?"hk":"near")+'"><h3>'+esc(ch.name)+' '+badge+'</h3>'+extra+'</div>';
}
// ===== 落户向导：先选通道，只显示对应字段（规则不变，仅做界面显隐）=====
const HKROUTE={
  common:["hk_healthy","hk_nocrime"],
  "001":["hk_edu","hk_gradyears","hk_fulltime","hk_neverrecv"],
  "002":["hk_age","hk_edu","hk_title","hk_skill","hk_ssyears","hk_ss","hk_shortage","hk_award"],
  "003":["hk_age","hk_osq","hk_osdeg","hk_visit"],
  "004":["hk_age","hk_gender","hk_permit","hk_pmyears","hk_still","hk_ownyears","hk_rentyears","hk_kinds"],
  "005":["hk_age","hk_taxlegal","hk_taxshare","hk_taxiit","hk_taxind","hk_sameent"],
  "006":["hk_age","hk_rel","hk_spyears","hk_szyears","hk_szfam"],
  "007":["hk_special","hk_specialkind"]
};
function hkCtlId(el){const c=el.querySelector("input[id],select[id]");return c?c.id:null;}
function clearHkCtl(id){const e=document.getElementById(id);if(!e)return;
  if(e.type==="checkbox")e.checked=(id==="hk_healthy"||id==="hk_nocrime");
  else if(e.tagName==="SELECT")e.value=(id==="hk_kinds"?"5":(id==="hk_gender"?"M":((id==="hk_rel"||id==="hk_specialkind")?"":"0")));
  else e.value="";}
function applyHkRoute(){
  const sel=document.querySelector('input[name=hk_route]:checked');const r=sel?sel.value:"";
  const fields=[...document.querySelectorAll("#hkBox .fld, #hkBox label.check")].filter(el=>!el.closest("#hkExtra"));
  if(!r){fields.forEach(el=>el.style.display="none");return;}
  const show=new Set(HKROUTE.common.concat(r==="all"?[]:(HKROUTE[r]||[])));
  fields.forEach(el=>{const id=hkCtlId(el);const vis=(r==="all")||show.has(id);
    el.style.display=vis?"":"none";
    if(!vis&&r!=="all")clearHkCtl(id);});
}
let LASTHK={eligible:[],near:[],p:null};
function resetHkForm(){
  ["hk_age","hk_gradyears","hk_ssyears","hk_pmyears","hk_ownyears","hk_rentyears","hk_spyears","hk_szyears","hk_taxlegal","hk_taxshare","hk_taxiit","hk_taxind"].forEach(i=>{const e=document.getElementById(i);if(e)e.value="";});
  const d={hk_gender:"M",hk_edu:"0",hk_title:"0",hk_skill:"0",hk_kinds:"5",hk_rel:"",hk_specialkind:""};
  Object.keys(d).forEach(i=>{const e=document.getElementById(i);if(e)e.value=d[i];});
  const off=["hk_fulltime","hk_neverrecv","hk_ss","hk_permit","hk_still","hk_shortage","hk_award","hk_osq","hk_osdeg","hk_visit","hk_sameent","hk_szfam","hk_special"];
  off.forEach(i=>{const e=document.getElementById(i);if(e)e.checked=false;});
  ["hk_healthy","hk_nocrime"].forEach(i=>{const e=document.getElementById(i);if(e)e.checked=true;});
  document.querySelectorAll('input[name=hk_route]').forEach(o=>o.checked=false);
  clearHkExtra();
  applyHkRoute();
}
function runHk(hkDom){
  if(!hkDom){LASTHK={eligible:[],near:[],p:null};return "";}
  const rp=collectHk().p; const elig=[],near=[];
  (hkDom.decisions||[]).forEach(ch=>{const d={status:ch.status,missing:ch.missing||[],branch_hit:ch.branch_hit,score:ch.score};if(d.status==="eligible")elig.push({ch:ch,d:d});else if(d.status==="near")near.push({ch:ch,d:d});});
  LASTHK={eligible:elig,near:near,p:rp};
  let h='<div class="seclevel">🏠 落户通道评估（应届 / 在职 / 留学引进 / 积分 / 纳税 / 随迁 / 特殊政策性）</div>';
  h+=elig.length?elig.map(x=>hkCard(x.ch,x.d)).join(""):'<div class="empty">按当前填写，7 条通道暂都不满足，展开下方“差条件”看缺口。</div>';
  if(near.length)h+='<div class="seclevel" style="font-size:12.5px;">差条件的落户通道（补齐后可走）</div>'+near.map(x=>hkCard(x.ch,x.d)).join("");
  h+='<div class="hktag" style="margin:4px 0 10px;">积分入户为年度全市排序竞争(名额内取前N名)，预估分不代表一定入围；纳税年龄50/翻倍55、随迁与积分的性别年龄上限等需按实际情况另核，结论以官方最新文件及窗口审核为准。</div>';
  return h;
}
// ===== 人才引进域（独立画像 kind=overseas，复用同一套 evaluate/estimate）=====
function osV(id,d){const el=document.getElementById(id);if(!el)return d;return el.value!==""?Number(el.value):d;}
function osS(id){const el=document.getElementById(id);return el?el.value:"other";}
function osC(id){const el=document.getElementById(id);return !!(el&&el.checked);}
function collectOs(){
  const p={kind:"overseas",
    os_age:osV("os_age",0),os_degree:osV("os_degree",0),os_district:osS("os_district"),
    os_anju_months:osV("os_anju_months",24),
    os_after2026:osC("os_after2026"),os_introduced:osC("os_introduced"),os_topschool:osC("os_topschool"),
    os_notrent:osC("os_notrent"),os_os3y:osC("os_os3y"),os_share:osC("os_share"),os_keyind:osC("os_keyind"),
    os_afterlg:osC("os_afterlg"),os_lghuji:osC("os_lghuji"),os_lgwork1y:osC("os_lgwork1y"),os_nosame:osC("os_nosame"),
    os_gotintro:osC("os_gotintro"),os_afterrenew1y:osC("os_afterrenew1y"),
    identities:osC("os_founder")?["os_founder"]:[]};
  const has=osV("os_age",0)>0||osV("os_degree",0)>0||osS("os_district")!=="other"
    ||["os_after2026","os_introduced","os_topschool","os_notrent","os_founder","os_os3y","os_share","os_keyind",
       "os_afterlg","os_lghuji","os_lgwork1y","os_nosame","os_gotintro","os_afterrenew1y"].some(osC);
  return {p:p,has:has};
}
function osCard(pol,p,ev){
  const review=pol.result_type==="review";
  let badge,cls;
  if(ev.st==="near"){cls="near";badge='<span class="badge b-warn">差一点·部分满足</span>';}
  else if(review){cls="match";badge='<span class="badge b-warn">符合申报资格·评审择优/名额有限</span>';}
  else{cls="match";badge='<span class="badge b-ok">符合条件</span>';}
  if(pol.level==="district")badge+='<span class="badge b-gray">区级叠加·'+esc(pol.district)+'</span>';
  let money="";
  if(ev.st==="match"){
    if(review){money='<div class="money">资助标准：'+esc(pol.std_name)+'（不按公式测算，评审后定档）</div>';}
    else{const est=estimate(p,pol.amount);money='<div class="money '+(est.val!=null?"est":"")+'">'+(est.val!=null?"参考可领：":"补贴标准：")+esc(est.txt)+'</div>';}
  }
  let estBlock="";
  if(ev.st==="match"&&!review){const est=estimate(p,pol.amount);
    if(est.lines&&est.lines.length)estBlock='<details><summary>金额测算明细</summary><div class="inner"><table class="estt">'+est.lines.map(r=>'<tr><td>'+esc(r[0])+'</td><td>'+esc(r[1])+'</td></tr>').join("")+'</table></div></details>';}
  const miss=ev.st==="near"?'<div class="miss">还需满足：'+ev.fails.map(esc).join('；')+'</div>':"";
  const da=(pol.district_awards&&pol.district_awards.length)?'<details><summary>区县配套对照('+pol.district_awards.length+'个区/镇街)</summary><div class="inner">'+pol.district_awards.map(x=>'<div class="mat"><b>'+esc(x.district||"")+'</b>　首次认定：'+esc(x.first||"—")+(x.renew?'；重新认定：'+esc(x.renew):"")+(x.move_in?'；'+esc(x.move_in):"")+(x.note?'（注：'+esc(x.note)+'）':"")+(x.url?'　<a href="'+esc(x.url)+'" target="_blank" rel="noopener" style="color:#1A5FB4;">依据原文</a>':"")+(x.basis?'<div style="color:#6b7280;font-size:12px;margin-top:2px;">依据：'+esc(x.basis)+'</div>':"")+'</div>').join("")+'</div></details>':"";const mat=pol.materials&&pol.materials.length?'<details><summary>所需材料('+(pol.material_count||pol.materials.length)+'项)</summary><div class="inner">'+pol.materials.map((x,i)=>'<div class="mat">'+(i+1)+'. '+esc(x)+'</div>').join("")+'</div></details>':"";
  return '<div class="card '+cls+'"><h3>'+esc(pol.name)+' '+badge+'</h3>'+money+estBlock+miss
    +'<details><summary>办理路径与流程</summary><div class="inner">'
    +'<div><b>政策原文：</b>'+(pol.guide_url?'<a href="'+pol.guide_url+'" target="_blank" rel="noopener" style="color:#1A5FB4;word-break:break-all;">查看原文</a>':"（以官方文号为准）")+'</div>'
    +'<div style="margin-top:4px;"><b>操作路径：</b><ol style="margin:4px 0 0 18px;padding:0;">'+pol.click_steps.map(s=>'<li style="margin-bottom:2px;">'+esc(s)+'</li>').join("")+'</ol></div>'
    +'<div style="margin-top:4px;"><b>标准/时限：</b>'+esc(pol.promise)+'</div>'
    +'<div style="margin-top:4px;"><b>办理说明：</b>'+esc(pol.where)+'</div>'
    +'<div style="margin-top:4px;"><b>流程：</b>'+esc(pol.process)+'</div></div></details>'
    +'<details><summary>⏰ 截止/时效规则（申报窗口·发放节奏）</summary><div class="inner"><div><b>申报窗口/期限：</b>'+esc(dlText(pol))+'</div><div style="margin-top:4px;"><b>标准/发放节奏：</b>'+esc(pol.promise)+'</div></div></details>'
    +da+mat
    +'<div class="hktag">'+esc(pol.notes||"")+'　依据：'+esc(pol.source_doc||"")+'</div></div>';
}
let LASTOS={match:[],near:[],p:null};
let OS_P=null;
function runOs(osDom){
  if(!osDom){LASTOS={match:[],near:0,p:null};return "";}
  const m=[],n=[];
  (osDom.match||[]).forEach(pol=>m.push(osCard(pol,OS_P,{st:"match",fails:[]})));
  (osDom.near||[]).forEach(pol=>n.push(osCard(pol,OS_P,{st:"near",fails:pol.missing||[]})));
  const matchItems=(osDom.match||[]).map(pol=>({pol:pol,est:pol.result_type==="review"?{txt:pol.std_name,kind:"review",val:null,lines:[]}:estimate(OS_P,pol.amount)}));
  LASTOS={match:matchItems,near:n.length,p:OS_P};
  let h='<div class="seclevel">🎓 人才引进政策（市级 + 区级叠加，现行有效口径 2026）</div>';
  h+=m.length?m.join(""):'<div class="empty">按当前填写暂没有完全符合的留学/青年人才项，补齐学历、首次在本市就业时间、知名高校等条件后再看。</div>';
  if(n.length)h+='<div class="seclevel" style="font-size:12.5px;">差一点的留学/青年人才项</div>'+n.join("");
  h+='<div class="hktag" style="margin:4px 0 10px;">旧市级“新引进人才租房和生活补贴”已自2021-9-1停发；本结果为现行青年人才/留学生政策。硕士、本科入户补贴市级只定上限、实际以各区指南为准；留学创业资助为评审名额制，只做资格预判、不承诺入选。</div>';
  return h;
}
// ===== 新增四域：企业扶持(用工+高企) / 人才安居 / 境外个税，通用结构渲染 =====
function enV(id,d){const el=document.getElementById(id);if(!el)return d;return el.value!==""?Number(el.value):d;}
function enS(id){const el=document.getElementById(id);return el?el.value:"";}
function enC(id){const el=document.getElementById(id);return !!(el&&el.checked);}
function collectEnt(){
  const p={kind:"unit",ent_scale:enS("en_scale"),ui_paid_months:enV("en_paidmonths",0),
    ui_premium_lastyear:enV("en_premium",0),staff_count:enV("en_staff",0),disabled_hire_count:enV("en_disabled",0),
    rd_expense:enV("en_rd",0),not_zombie:enC("en_notzombie"),
    no_layoff:enC("en_nolayoff"),layoff_rate_ok:enC("en_layoffok"),
    is_hnte:enC("en_hnte"),is_sme_tech:enC("en_smetech"),hnte_certified:enC("en_hntecert"),
    contract_years:enV("en_contract",0),ent_ss_months:enV("en_ssmonths",0),
    hire_keygroup_count:enV("en_keygroup",0),hire_veteran_count:enV("en_vet",0),
    hire_grad2y_count:enV("en_grad2y",0),mom_post_count:enV("en_mom",0),
    disabled_ratio_below_quota:enC("en_belowquota"),mom_post_base_certified:enC("en_mombase"),
    is_small_low_profit:enC("en_small_low_profit"),is_vat_small_scale:enC("en_vat_small_scale"),
    biz_reg_months:enV("en_bizreg",0),identities:[].slice.call(document.querySelectorAll('#entBox input[data-ff="identities"]:checked')).map(function(e){return e.dataset.val;}),
    apprentice_count:enV("en_apprentice_count",0),hire_count:enV("en_hire_count",0),hire_employdiff_count:enV("en_hire_employdiff_count",0),hire_new_nonlocal_count:enV("en_hire_new_nonlocal_count",0),hire_poverty_count:enV("en_hire_poverty_count",0),hire_trainee_count:enV("en_hire_trainee_count",0),hire_unemp6m_count:enV("en_hire_unemp6m_count",0),hire_veteran_within1y_count:enV("en_hire_veteran_within1y_count",0),hkmo_intern_months:enV("en_hkmo_intern_months",0),incubated_success_count:enV("en_incubated_success_count",0),jiazheng_avg_pay_heads:enV("en_jiazheng_avg_pay_heads",0),job_intro_count:enV("en_job_intro_count",0),monitor_worker_count:enV("en_monitor_worker_count",0),public_welfare_heads:enV("en_public_welfare_heads",0),student_eval_count:enV("en_student_eval_count",0),unemp_insurance_heads:enV("en_unemp_insurance_heads",0),bought_commercial_insurance:enC("en_bought_commercial_insurance"),bought_intern_insurance:enC("en_bought_intern_insurance"),founder_training_selected:enC("en_founder_training_selected"),free_skill_eval:enC("en_free_skill_eval"),has_grassroots_post:enC("en_has_grassroots_post"),has_public_welfare_post:enC("en_has_public_welfare_post"),has_student_mid_cert:enC("en_has_student_mid_cert"),has_training_cert:enC("en_has_training_cert"),has_worker_skill_cert:enC("en_has_worker_skill_cert"),hire_elig_ratio_ok:enC("en_hire_elig_ratio_ok"),hire_keygroup_ratio_ok:enC("en_hire_keygroup_ratio_ok"),hkmo_intern:enC("en_hkmo_intern"),incubate_over_1y:enC("en_incubate_over_1y"),is_employment_monitor_point:enC("en_is_employment_monitor_point"),is_labor_dispatch:enC("en_is_labor_dispatch"),is_legal_rep:enC("en_is_legal_rep"),nanyue_jiazheng_registered:enC("en_nanyue_jiazheng_registered"),no_credit_violation:enC("en_no_credit_violation"),no_wage_ss_arrears:enC("en_no_wage_ss_arrears"),normal_operation:enC("en_normal_operation"),pay_trainee_80pct:enC("en_pay_trainee_80pct"),run_apprentice_program:enC("en_run_apprentice_program"),run_training_class:enC("en_run_training_class"),trainee_ratio_ok:enC("en_trainee_ratio_ok"),ent_types:[...document.querySelectorAll('#entBox input[data-ff="ent_types"]:checked')].map(e=>e.dataset.val)};
  const has=enS("en_scale")!==""||enV("en_paidmonths",0)>0||enV("en_premium",0)>0||enV("en_staff",0)>0
    ||enV("en_disabled",0)>0||enV("en_rd",0)>0||enV("en_keygroup",0)>0||enV("en_vet",0)>0||enV("en_grad2y",0)>0
    ||enV("en_contract",0)>0||enV("en_ssmonths",0)>0||enV("en_mom",0)>0||enV("en_bizreg",0)>0
    ||["en_notzombie","en_nolayoff","en_layoffok","en_hnte","en_smetech","en_hntecert","en_belowquota","en_mombase","en_small_low_profit","en_vat_small_scale"].some(enC)
    ||_wbExCtl("entBox");
  return {p:p,has:has};
}
function hsV(id,d){const el=document.getElementById(id);if(!el)return d;return el.value!==""?Number(el.value):d;}
function collectHs(){
  const idv=(document.getElementById("hs_identity")||{}).value||"";
  const p={kind:"person",sz_social_years:hsV("hs_ssyears",0),sz_work_days:hsV("hs_workdays",0),
    has_sz_hukou:document.getElementById("hs_huji").checked,no_self_house:document.getElementById("hs_nohouse").checked,
    no_transfer_3y:document.getElementById("hs_notransfer").checked,single_age_ok:document.getElementById("hs_single35").checked,is_family_household:document.getElementById("hs_family").checked,
    no_housing_benefit:document.getElementById("hs_nobenefit").checked,income_ok:document.getElementById("hs_incomeok").checked,
    is_high_end_talent:document.getElementById("hs_highend").checked,is_scarce_talent:document.getElementById("hs_scarce").checked,
    pay_iit_sz:document.getElementById("hs_payiit").checked,in_key_industry:document.getElementById("hs_keyind").checked,
    no_crime_3y:document.getElementById("hs_nocrime").checked,identities:idv?[idv]:[]};
  const has=hsV("hs_ssyears",0)>0||hsV("hs_workdays",0)>0||idv!==""
    ||["hs_huji","hs_nohouse","hs_notransfer","hs_single35","hs_family","hs_nobenefit","hs_incomeok","hs_highend","hs_scarce","hs_payiit","hs_keyind","hs_nocrime"].some(i=>document.getElementById(i).checked);
  return {p:p,has:has};
}
function dlText(pol){const d=pol.deadline;if(!d)return"";if(typeof d==="string")return d;
  const base=[d.text,d.cycle].filter(Boolean).join(" ");
  const et=dlExpireText(d);            // 标了执行状态时带说明，不裸印日期
  if(et&&base.indexOf(et)<0)return(base?base+" ":"")+et;
  return base||(d.expire||d.expire_text||"");}
function genCard(pol,st,fails){
  const rt=pol.result_type,review=rt==="review",channel=rt==="channel";
  let badge,cls;
  if(st==="near"){cls="near";badge='<span class="badge b-warn">差一点·部分满足</span>';}
  else if(review){cls="match";badge='<span class="badge b-warn">符合申报资格·评审/核准择优</span>';}
  else if(channel){cls="match";badge='<span class="badge b-ok">符合资格条件</span>';}
  else{cls="match";badge='<span class="badge b-ok">符合条件</span>';}
  if(pol.ptype)badge+='<span class="badge" style="background:#EEF2F7;color:#44566B;border:1px solid #D5DEEA;">'+esc(pol.ptype+(pol.ptype_detail?"（"+pol.ptype_detail+"）":""))+'</span>';
  const amt=pol.amount&&pol.amount.text?pol.amount.text:"";
  const money=(st==="match"&&amt)?'<div class="money">'+(channel?"资格/供给说明：":"补贴/优惠标准：")+esc(amt)+'</div>':"";
  const miss=(st==="near"&&fails&&fails.length)?'<div class="miss">还需满足：'+fails.map(esc).join('；')+'</div>':"";
  const mats=(pol.materials&&pol.materials.length)?'<details><summary>所需材料('+(pol.material_count||pol.materials.length)+'项)</summary><div class="inner">'+pol.materials.map((x,i)=>'<div class="mat">'+(i+1)+'. '+esc(x)+'</div>').join("")+'</div></details>':"";
  const rows=[];
  if(pol.guide_url)rows.push('<div><b>政策原文：</b><a href="'+pol.guide_url+'" target="_blank" rel="noopener" style="color:#1A5FB4;word-break:break-all;">查看原文</a></div>');
  if(pol.how)rows.push('<div style="margin-top:4px;"><b>办理路径：</b>'+esc(pol.how)+'</div>');
  if(pol.process)rows.push('<div style="margin-top:4px;"><b>流程：</b>'+esc(pol.process)+'</div>');
  if(pol.where)rows.push('<div style="margin-top:4px;"><b>办理说明：</b>'+esc(pol.where)+'</div>');
  const path=rows.length?'<details><summary>办理路径与流程</summary><div class="inner">'+rows.join("")+'</div></details>':"";
  const dt=dlText(pol);
  const time=dt?'<details><summary>⏰ 截止/时效规则</summary><div class="inner">'+esc(dt)+'</div></details>':"";
  const tc=(pol.to_collect&&pol.to_collect.length)?'<div class="hktag" style="color:#8A5A00;">该项仍在向官方补全：'+pol.to_collect.map(esc).join('；')+'（当前为L'+(pol.depth||"?")+'口径，以官方最新文件为准）</div>':"";
  return '<div class="card '+cls+'"><h3>'+esc(pol.name)+' '+badge+'</h3>'+money+miss+path+time+mats+tc
    +'<div class="hktag">细度L'+esc(pol.depth||"?")+'　依据：'+esc(pol.source_doc||"")+'</div></div>';
}
function genDomSection(dom,p,title,emptyTxt){
  const m=[],n=[];
  (dom&&dom.match||[]).forEach(pol=>m.push({pol:pol,html:genCard(pol,"match",[])}));
  (dom&&dom.near||[]).forEach(pol=>n.push({pol:pol,html:genCard(pol,"near",pol.missing||[])}));
  let h='<div class="seclevel">'+title+'</div>';
  h+=m.length?m.map(x=>x.html).join(""):'<div class="empty">'+emptyTxt+'</div>';
  if(n.length)h+='<div class="seclevel" style="font-size:12.5px;">差一点（补齐后符合）</div>'+n.map(x=>x.html).join("");
  return {html:h,match:m,near:n.length};
}
let LASTENT={match:[],near:0,p:null};
function runEnt(entDom,tcDom){
  const a=genDomSection(entDom,LASTENT.p,"🏢 企业用工扶持（稳岗返还·残保金减免）","按当前填写暂无符合的用工扶持项，可补企业规模、失业保险缴费、职工人数等。");
  const b=genDomSection(tcDom,LASTENT.p,"🔬 科技企业扶持（高企所得税15%·研发加计扣除·亏损结转·认定资助）","按当前填写暂无符合的科技扶持项；持有高企证书或有研发费用即可勾选对应项。");
  LASTENT={match:a.match.concat(b.match),near:a.near+b.near,p:LASTENT.p};
  return a.html+b.html;
}
let LASTHS={match:[],near:0,p:null};
function runHs(hsDom,gbaDom){
  const a=genDomSection(hsDom,LASTHS.p,"🏘️ 人才安居住房（可售人才房·配售型保障房·公租房资格）","按当前填写暂无符合的住房资格，通常需本地户籍、无房并满足社保年限。");
  const b=genDomSection(gbaDom,LASTHS.p,"🌏 大湾区境外人才个税差额补贴（高端/紧缺，税负超15%部分返还、封顶500万）","按当前填写暂无符合的境外个税补贴；需境外身份、在本市工作超90天并纳税。");
  LASTHS={match:a.match.concat(b.match),near:a.near+b.near,p:LASTHS.p};
  return a.html+b.html;
}
function genItemText(pol){
  const L=[];L.push("【"+pol.name+"】"+(pol.ptype?("（"+pol.ptype+(pol.ptype_detail?"（"+pol.ptype_detail+"）":"")+"）"):""));
  if(pol.amount&&pol.amount.text)L.push("- 标准/说明："+pol.amount.text);
  if(pol.district_awards&&pol.district_awards.length){L.push("- 区县配套对照（"+pol.district_awards.length+"个区/镇街）：");pol.district_awards.forEach(x=>L.push("    · "+x.district+"：首次认定 "+(x.first||"—")+(x.renew?"；重新认定 "+x.renew:"")+(x.basis?"（依据："+x.basis+"）":"")));}if(pol.materials&&pol.materials.length){L.push("- 所需材料（"+(pol.material_count||pol.materials.length)+"项）：");pol.materials.forEach((mm,i)=>L.push("    "+(i+1)+") "+mm));}
  if(pol.how)L.push("- 办理路径："+pol.how);
  if(pol.process)L.push("- 流程："+pol.process);
  if(pol.where)L.push("- 办理说明："+pol.where);
  const dt=dlText(pol);if(dt)L.push("- 截止/时效："+dt);
  if(pol.guide_url)L.push("- 政策原文："+pol.guide_url);
  if(pol.source_doc)L.push("- 政策依据："+pol.source_doc);
  if(pol.to_collect&&pol.to_collect.length)L.push("- 待官方补全："+pol.to_collect.join("；"));
  return L.join("\n");
}
function genChecklistLines(title,last,idx){
  const L=[];if(!last.p||!last.match.length)return L;
  L.push(idx+"、"+title+"（符合 "+last.match.length+" 项）");
  L.push("--------------------------------------------------");
  last.match.forEach((it,i)=>{L.push((i+1)+". "+genItemText(it.pol));L.push("");});
  L.push("");return L;
}
function resetEntForm(){["en_paidmonths","en_premium","en_staff","en_disabled","en_rd","en_contract","en_ssmonths","en_keygroup","en_vet","en_grad2y","en_mom"].forEach(i=>{const e=document.getElementById(i);if(e)e.value="";});
  document.getElementById("en_scale").value="";
  ["en_notzombie","en_nolayoff","en_layoffok","en_hnte","en_smetech","en_hntecert","en_belowquota","en_mombase"].forEach(i=>{document.getElementById(i).checked=false;});
  [].slice.call(document.querySelectorAll("#entBox [data-wbex]")).forEach(e=>{if(e.type==="checkbox")e.checked=false;else e.value="";});}
function resetHsForm(){["hs_ssyears","hs_workdays"].forEach(i=>{const e=document.getElementById(i);if(e)e.value="";});
  document.getElementById("hs_identity").value="";
  ["hs_huji","hs_nohouse","hs_notransfer","hs_single35","hs_family","hs_nobenefit","hs_incomeok","hs_highend","hs_scarce","hs_payiit","hs_keyind","hs_nocrime"].forEach(i=>{document.getElementById(i).checked=false;});}
function syncLgExtra(){const d=document.getElementById("os_district").value;document.querySelectorAll(".lgonly").forEach(e=>{e.style.display=d==="longgang"?"":"none";});}
document.getElementById("os_district").addEventListener("change",syncLgExtra);
syncLgExtra();
function resetOsForm(){
  ["os_age"].forEach(i=>{const e=document.getElementById(i);if(e)e.value="";});
  const d={os_degree:"0",os_district:"other",os_anju_months:"24"};Object.keys(d).forEach(i=>{const e=document.getElementById(i);if(e)e.value=d[i];});
  ["os_after2026","os_introduced","os_topschool","os_notrent","os_founder","os_os3y","os_share","os_keyind","os_afterlg","os_lghuji","os_lgwork1y","os_nosame","os_gotintro","os_afterrenew1y"].forEach(i=>{const e=document.getElementById(i);if(e)e.checked=false;});
  if(typeof syncLgExtra==="function")syncLgExtra();
}
function osItemText(it){
  const pol=it.pol,est=it.est,L=[];
  const tag=pol.level==="district"?"（区级叠加 · "+(pol.district||"")+"）":"";
  L.push("【"+pol.name+"】"+tag+(pol.result_type==="review"?"（评审择优，不承诺入选）":""));
  L.push("- 标准事项名："+pol.std_name);
  if(est){
    L.push("- 参考金额/方式："+est.txt);
    if(est.lines&&est.lines.length)est.lines.forEach(r=>L.push("    · "+r[0]+"："+r[1]));
  }
  if(pol.district_awards&&pol.district_awards.length){L.push("- 区县配套对照（"+pol.district_awards.length+"个区/镇街）：");pol.district_awards.forEach(x=>L.push("    · "+x.district+"：首次认定 "+(x.first||"—")+(x.renew?"；重新认定 "+x.renew:"")+(x.basis?"（依据："+x.basis+"）":"")));}if(pol.materials&&pol.materials.length){
    L.push("- 所需材料（"+(pol.material_count||pol.materials.length)+"项）：");
    pol.materials.forEach((mm,i)=>L.push("    "+(i+1)+") "+mm));
  }
  if(pol.click_steps&&pol.click_steps.length){
    L.push("- 电脑/网页操作路径：");pol.click_steps.forEach((s,i)=>L.push("    "+(i+1)+". "+s));
  }
  if(pol.where)L.push("- 办理说明："+pol.where);
  if(pol.process)L.push("- 办理流程："+pol.process);
  if(pol.promise)L.push("- 标准/发放节奏："+pol.promise);
  if(pol.deadline)L.push("- 截止/时效："+dlText(pol));
  if(pol.guide_url)L.push("- 政策原文："+pol.guide_url);
  if(pol.source_doc)L.push("- 政策依据："+pol.source_doc);
  if(pol.notes)L.push("- 备注："+pol.notes);
  return L.join("\n");
}
function osChecklistLines(idx){
  const L=[];if(!LASTOS.p||!LASTOS.match.length)return L;
  L.push((idx||"四")+"、人才引进政策（现行2026口径，共 "+LASTOS.match.length+" 项）");
  L.push("--------------------------------------------------");
  LASTOS.match.forEach((it,i)=>{L.push((i+1)+". "+osItemText(it));L.push("");});
  L.push("  注：本硕入户补贴以各区指南为准；留学创业资助评审择优、不承诺入选；旧市级租房生活补贴已停发；金额为规则估算，以官方最新文件及窗口审核为准。");
  L.push("");
  return L;
}
// ── 下线状态（valid）标签与判定（2026-10-10）──────────────────────
// 与后端 gate_validate.VALID_VALID / contract.md §10.2 / pipeline/enum_map.json 同源。
// 改动 valid 枚举必须同步四处：闸门白名单 · schema.json · contract.md · enum_map.json，
// 外加前端两份（本文件 + demo_api.html）与 field_contract.json 重新生成。
const VLABEL={active:"",renamed:"已更名·按新事项申报",exited:"已退出实施·不再新申报",
              merged:"重复录入·已合并",superseded:"已被新版替代·按新版申报"};
// 已下线状态：不进「你能申报」的匹配结果与金额测算（仍以「备查」区块展示）
const VOFF=["exited","merged","superseded"];
function vlabel(v){return VLABEL[v]||"";}
function voff(v){return VOFF.indexOf(v)>=0;}

// ── 执行状态（deadline.exec_status）标签（2026-10-18）──────────────
// ★ 真值源 = `pipeline/enum_map.json::exec_status`。这里是**前端副本**，
//   由 tests/test_exec_status.py::E9 断言与本文件逐字一致（改一处不改另一处会红）。
// 语义：`valid` 管**记录**是否还在库（active/exited…），本枚举管**文件**是否届满却仍在执行。
// 两者正交 —— 一条记录可以 active（仍可申报）而文件 expired_continuing（依据文件已届满）。
const EXEC_LABEL={expired_continuing:"文件已届满·仍在执行",
                  pending_renewal:"文件已届满·续期未定",
                  expired_stopped:"文件已届满·已停止执行"};
function execLabel(d){return (d&&d.exec_status)?(EXEC_LABEL[d.exec_status]||""):"";}
// 颜色：仍在执行=琥珀（提醒但仍可办）；已停止=红；续期未定=灰蓝
function execChip(d){
  const lb=execLabel(d); if(!lb)return"";
  const st=d.exec_status;
  const sty = st==="expired_stopped" ? "background:#FDECEC;color:#C0392B;border:1px solid #F5C6C6;"
            : st==="pending_renewal" ? "background:#EEF2F7;color:#4A5568;border:1px solid #CBD5E0;"
            : "background:#FFF4E0;color:#8A5A00;border:1px solid #F0D9A8;";
  return '<span class="chip" style="'+sty+'" title="'+esc(d.exec_note||"")+'">⚑ '+esc(lb)+'</span>';
}
// 有效期文本：标了执行状态时**必须把说明一起印出来**，不许只印日期
// （与 pipeline/mappers.deadline_text() 同一口径：文件届满 ≠ 政策失效）
function dlExpireText(d){
  if(!d||typeof d!=="object")return "";
  const ex=d.expire||d.expire_text||"";
  if(!d.exec_status)return ex;
  const note=d.exec_note||"";
  return (ex&&/^\d{4}-\d{2}-\d{2}$/.test(ex)?"有效期至 "+ex:"") + (note?("；"+note):"");
}

function polCard(pol,p,ev){
  const est=estimate(p,pol.amount);
  let badge='<span class="badge b-ok">符合条件</span>';
  if(pol.valid==="renamed")badge+='<span class="badge b-warn">'+esc(vlabel("renamed"))+'</span>';
  else if(voff(pol.valid))badge='<span class="badge b-warn">'+esc(vlabel(pol.valid))+'</span>';
  const ptag=pol.ptype?'<span class="badge" style="background:#EEF2F7;color:#44566B;border:1px solid #D5DEEA;">类型：'+esc(pol.ptype+(pol.ptype_detail?"（"+pol.ptype_detail+"）":""))+'</span>':"";
  let cls="match";
  if(ev.st==="near"){cls="near";badge='<span class="badge b-warn">差一点·部分满足</span>';}
  const da=(pol.district_awards&&pol.district_awards.length)?'<details><summary>区县配套对照('+pol.district_awards.length+'个区/镇街)</summary><div class="inner">'+pol.district_awards.map(x=>'<div class="mat"><b>'+esc(x.district||"")+'</b>　首次认定：'+esc(x.first||"—")+(x.renew?'；重新认定：'+esc(x.renew):"")+(x.move_in?'；'+esc(x.move_in):"")+(x.note?'（注：'+esc(x.note)+'）':"")+(x.url?'　<a href="'+esc(x.url)+'" target="_blank" rel="noopener" style="color:#1A5FB4;">依据原文</a>':"")+(x.basis?'<div style="color:#6b7280;font-size:12px;margin-top:2px;">依据：'+esc(x.basis)+'</div>':"")+'</div>').join("")+'</div></details>':"";let mat="";
  if((pol.materials||[]).length)mat='<details><summary>所需材料('+(pol.material_count||pol.materials.length)+'项)</summary><div class="inner">'+pol.materials.map((x,i)=>'<div class="mat">'+(i+1)+'. '+esc(x)+'</div>').join("")+'</div></details>';
  let miss=ev.st==="near"?'<div class="miss">还需满足：'+ev.fails.map(esc).join('；')+'</div>':"";
  const moneyLabel=pol.ptype==="创业担保贷款贴息"?"贷款额度/贴息：":pol.ptype==="税收减免"?"税收减免额度：":pol.ptype==="评审资助"?"资助标准(评审)：":(est.val!=null?"参考可领：":"补贴标准：");
  let money=(ev.st==="match"&&!voff(pol.valid))?'<div class="money '+(est.val!=null?"est":"")+'">'+moneyLabel+esc(est.txt)+'</div>':"";
  let estBlock=(ev.st==="match"&&est.lines&&est.lines.length)?'<details><summary>金额测算明细（怎么算出来的）</summary><div class="inner"><table class="estt">'
    +est.lines.map(r=>'<tr><td>'+esc(r[0])+'</td><td>'+esc(r[1])+'</td></tr>').join("")+'</table></div></details>':"";
  return '<div class="card '+cls+'"><h3>'+esc(pol.name)+' '+badge+ptag+'</h3>'+money+estBlock+miss
    +'<details><summary>办理路径与流程</summary><div class="inner">'
    +'<div style="margin-top:2px;"><b>办理入口：</b>'
    +(pol.apply_url?'<a class="ovbtn pri" style="display:inline-block;padding:4px 12px;font-size:13px;text-decoration:none;" href="'+pol.apply_url+'" target="_blank" rel="noopener">🚀 直达申报系统/办事窗口 ↗</a>&nbsp;':'')
    +(pol.guide_url?'<a href="'+pol.guide_url+'" target="_blank" rel="noopener" style="color:#1A5FB4;word-break:break-all;">📄 查看政策原文</a>':'<span style="color:#6B7280;font-size:12.5px;">（政策原文以官方文号为准，未挂外部链接）</span>')
    +'</div>'
    +(pol.apply_url?'':'<div style="margin-top:3px;font-size:12px;color:#6B7280;">💡 本项暂无统一在线申报入口：请到<b>当地省/市政务服务网</b>搜索「'+esc(pol.std_name||pol.name)+'」办理（广东 gdzwfw.gov.cn ｜ 浙江 zjzwfw.gov.cn ｜ 江苏 jszwfw.gov.cn ｜ 广西 zwfw.gxzf.gov.cn）；落户/户政类以当地公安局窗口为准。</div>')
    +'<div style="margin-top:4px;"><b>操作路径：</b><ol style="margin:4px 0 0 18px;padding:0;">'+(pol.click_steps||[]).map(function(s){return '<li style="margin-bottom:2px;">'+esc(s)+'</li>';}).join("")+'</ol></div>'
    +'<div style="margin-top:4px;"><b>时限/跑动：</b>'+esc(pol.promise)+'</div>'
    +'<div style="margin-top:4px;"><b>办理说明：</b>'+esc(pol.where)+'</div>'
    +'<div style="margin-top:4px;"><b>流程：</b>'+esc(pol.process)+'</div></div></details>'
    +da+mat
    +'<details><summary>截止/时效规则</summary><div class="inner">'+esc((pol.deadline||{}).text||"以当年官方申报通知为准")+(dlExpireText(pol.deadline)?'<br><b>状态/有效期：</b>'+esc(dlExpireText(pol.deadline)):"")+(execLabel(pol.deadline)?'<br>'+execChip(pol.deadline):"")+'</div></details></div>';
}

// ===== 客户版：申报清单 =====
let LAST={p:null,match:[],nearN:0};
// ===== 贴牌（机构顾问）：本机记住，用于清单抬头/落款与打印版 =====
let BRAND={org:"",advisor:"",contact:"",qr:""};
function brandLoad(){try{const s=localStorage.getItem("sz_demo_brand");if(s)BRAND=Object.assign(BRAND,JSON.parse(s));}catch(e){}}
function brandSave(){try{localStorage.setItem("sz_demo_brand",JSON.stringify(BRAND));}catch(e){}}
function brandHas(){return !!(BRAND.org||BRAND.advisor||BRAND.contact||BRAND.qr);}
function isClOpen(){return !document.getElementById("clMask").classList.contains("hide");}
function brandTextHead(){return brandHas()?[BRAND.org?("【"+BRAND.org+" · 为您专属整理】"):"【为您专属整理】"]:[];}
function brandTextFoot(){
  if(!brandHas())return [];
  return ["--------------------------------------------------",
    "本清单由 "+(BRAND.org||"您的服务机构")+" 整理提供"+(BRAND.advisor?("　顾问："+BRAND.advisor):"")+(BRAND.contact?("　咨询电话/微信："+BRAND.contact):""),
    "政策匹配与金额为规则估算，仅供申报准备参考，最终以官方文件及窗口审核为准。"];
}
function brandHtmlHead(){
  if(!brandHas())return "";
  let h='<div style="text-align:center;border-bottom:2px solid #2B6CB0;padding-bottom:8px;margin-bottom:12px;">';
  if(BRAND.org)h+='<div style="font-size:22px;font-weight:700;color:#1F4E79;">'+esc(BRAND.org)+'</div>';
  h+='<div style="font-size:12px;color:#4A5568;margin-top:4px;">'+(BRAND.advisor?("申报顾问："+esc(BRAND.advisor)+"　"):"")+(BRAND.contact?("咨询电话/微信："+esc(BRAND.contact)):"")+'</div></div>';
  return h;
}
function initBrand(){
  brandLoad();
  [["br_org","org"],["br_advisor","advisor"],["br_contact","contact"]].forEach(pair=>{
    const el=document.getElementById(pair[0]);el.value=BRAND[pair[1]]||"";
    el.oninput=()=>{BRAND[pair[1]]=el.value;brandSave();if(isClOpen())refreshChecklist();};
  });
  const thumb=document.getElementById("qrThumb"),clearBtn=document.getElementById("qrClear");
  if(BRAND.qr){thumb.src=BRAND.qr;thumb.style.display="inline-block";clearBtn.style.display="inline";}
  document.getElementById("br_qr").onchange=function(){
    const f=this.files&&this.files[0];if(!f)return;
    if(f.size>2*1024*1024){alert("图片请控制在2MB以内，便于嵌入文档。");return;}
    const r=new FileReader();
    r.onload=()=>{BRAND.qr=r.result;brandSave();thumb.src=BRAND.qr;thumb.style.display="inline-block";clearBtn.style.display="inline";};
    r.readAsDataURL(f);
  };
  clearBtn.onclick=()=>{BRAND.qr="";brandSave();thumb.removeAttribute("src");thumb.style.display="none";clearBtn.style.display="none";document.getElementById("br_qr").value="";};
}
const KINDNAME={person:"个人求职者/毕业生",unit:"用人单位",entrepreneur:"自主创业者"};
function tagLabel(k,val){let hit=null;FORM[k].tags.options.forEach(o=>{if(o[0]===val)hit=o[1];});return hit||val;}
function pSummary(p){
  if(!p)return ["（本次未填写就业创业补贴画像；如需要可在左侧补填）"];
  let L=["主体类型："+(KINDNAME[p.kind]||p.kind)];
  const tf=FORM[p.kind].tags.field||"identities", tags=p[tf]||[];
  if(tags.length)L.push("身份/类型："+tags.map(v=>tagLabel(p.kind,v)).join("、"));
  FORM[p.kind].nums.forEach(n=>{const v=Number(p[n[0]]||0);if(v>0)L.push(n[1]+"："+v);});
  FORM[p.kind].bools.forEach(b=>{if(p[b[0]])L.push(b[1]+"：是");});
  return L;
}
function itemText(it){
  const pol=it.pol,est=it.est,L=[];
  L.push("【"+pol.name+"】"+(pol.ptype?"（类型："+pol.ptype+(pol.ptype_detail?"（"+pol.ptype_detail+"）":"")+"）":"")+(vlabel(pol.valid)?"（"+vlabel(pol.valid)+"）":""));
  L.push("- 标准事项名："+pol.std_name+(pol.guide_area?("（样例："+pol.guide_area+"，进入后切换到本单位/本人所在区）"):""));
  L.push("- 参考金额："+est.txt);
  if(est.lines&&est.lines.length)est.lines.forEach(r=>L.push("    · "+r[0]+"："+r[1]));if(pol.district_awards&&pol.district_awards.length){L.push("- 区县配套对照（"+pol.district_awards.length+"个区/镇街）：");pol.district_awards.forEach(x=>L.push("    · "+x.district+"：首次认定 "+(x.first||"—")+(x.renew?"；重新认定 "+x.renew:"")+(x.basis?"（依据："+x.basis+"）":"")));}
  L.push("- 所需材料（"+(pol.material_count||pol.materials.length)+"项）：");
  pol.materials.forEach((mm,i)=>L.push("    "+(i+1)+") "+mm));
  L.push("- 在线办理入口："+(pol.apply_url?pol.apply_url:("请到当地省/市政务服务网搜索「"+pol.std_name+"」")));
  L.push("- 操作路径：");pol.click_steps.forEach((s,i)=>L.push("    "+(i+1)+". "+s));
  L.push("- 时限/跑动："+pol.promise);
  L.push("- 截止/时效："+dlText(pol));
  return L.join("\n");
}
function pad2(x){return String(x).padStart(2,"0");}
function empWinChecklistLines(){
  const L=[];if(!LAST||!LAST.match||!LAST.match.length)return L;
  L.push("  ▶ 全市公共就业（创业）服务窗口名录（共 "+EMPWIN.count+" 个，来源官方；单位按注册地、个人按就业地、创业者按企业注册地选区/街道）：");
  const g={};EMPWIN.windows.forEach(w=>{(g[w.district]=g[w.district]||[]).push(w);});
  Object.keys(g).forEach(d=>{L.push("    【"+d+"·"+g[d].length+"个】");g[d].forEach(w=>L.push("      "+w.level+"｜"+w.name+"｜"+w.addr+"｜电话 "+w.tel+"｜"+w.time));});
  L.push("    咨询："+EMPWIN.hotline);
  L.push("");
  return L;
}
function hkItemText(x){
  const ch=x.ch,d=x.d,L=[];
  let s="[可走] "+ch.name+(d.branch_hit?("（命中路径："+d.branch_hit+"）"):"");
  if(d.score!=null)s+="；预估积分约 "+d.score+" 分（年度排序竞争，不承诺入围）";
  L.push(s);
  if(ch.applicant_detail)L.push("- 适用对象："+ch.applicant_detail);
  if(ch.cond&&ch.cond.base_must&&ch.cond.base_must.length)L.push("- 基本条件："+ch.cond.base_must.map(c=>c.label).join("；"));
  if(ch.materials&&ch.materials.length){
    L.push("- 所需材料（"+ch.materials.length+"项）：");
    ch.materials.forEach((m,i)=>L.push("    "+(i+1)+") "+m));
  }
  if(ch.click_steps&&ch.click_steps.length){
    L.push("- 电脑/网页操作路径：");ch.click_steps.forEach((s,i)=>L.push("    "+(i+1)+". "+s));
  }
  if(ch.promise)L.push("- 办理说明/时限："+ch.promise);
  if(ch.deadline)L.push("- 截止/时效："+dlText(ch));
  if(ch.guide_url)L.push("- 政策原文："+ch.guide_url);
  if(ch.source_doc)L.push("- 政策依据："+ch.source_doc);
  if(ch.notes)L.push("- 备注："+ch.notes);
  return L.join("\n");
}
function hkChecklistLines(idx){
  const L=[];if(!LASTHK.p||(!LASTHK.eligible.length&&!LASTHK.near.length))return L;
  L.push((idx||"三")+"、落户通道评估（应届/在职/留学引进/积分/纳税/随迁，可走 "+LASTHK.eligible.length+" 条）");
  L.push("--------------------------------------------------");
  LASTHK.eligible.forEach((x,i)=>{L.push((i+1)+". "+hkItemText(x));L.push("");});
  LASTHK.near.forEach(x=>L.push("  [暂不满足] "+x.ch.name+"，还需："+x.d.missing.join("；")));
  L.push("  注：积分入户为年度全市排序竞争，预估分不代表入围；落户结论以官方最新文件及窗口审核为准。");
  L.push("");
  return L;
}
function checklistText(){
  const now=new Date();
  const ts=now.getFullYear()+"-"+pad2(now.getMonth()+1)+"-"+pad2(now.getDate())+" "+pad2(now.getHours())+":"+pad2(now.getMinutes());
  let one=0,mon=0;
  LAST.match.forEach(it=>{if(it.est.kind==="month_x_count")mon+=(it.est.val||0);else if(["once","once_x_count","tiered_hire"].includes(it.est.kind))one+=(it.est.val||0);});
  let L=[];
  L.push("政策匹配 · 个性化申报清单（就业创业 / 落户 / 留学人才 / 企业扶持 / 人才安居 / 境外个税）");
  brandTextHead().forEach(x=>L.push(x));
  L.push("生成时间："+ts+"　|　数据口径：填入库中的政策条目，请在对外交付前自行核对原文与时效");
  L.push("==================================================");
  L.push("一、申报主体画像");
  pSummary(LAST.p).forEach(x=>L.push("  "+x));
  L.push("");
  const CN=["一","二","三","四","五"];let sec=2;
  if(LAST.match.length){
    L.push(CN[sec-1]+"、可申领就业创业补贴（共 "+LAST.match.length+" 项）");
    L.push("  一次性补贴参考合计：约 "+one.toLocaleString()+" 元"+(mon?("；按月发放项合计约 "+mon.toLocaleString()+" 元/月（发放年限另计，不并入一次性合计）"):""));
    L.push("--------------------------------------------------");
    LAST.match.forEach((it,i)=>{L.push((i+1)+". "+itemText(it));L.push("");});
    if(LAST.nearN)L.push("备注：另有 "+LAST.nearN+" 项“差一点”补贴，补齐条件后可申报（详见匹配结果区）。");
    L.push("");sec++;
  }
  const hkLines=hkChecklistLines(CN[sec-1]);if(hkLines.length){hkLines.forEach(x=>L.push(x));sec++;}
  const osLines=osChecklistLines(CN[sec-1]);if(osLines.length){osLines.forEach(x=>L.push(x));sec++;}
  const entLines=genChecklistLines("企业扶持（用工降本·高企研发）",LASTENT,CN[sec-1]);if(entLines.length){entLines.forEach(x=>L.push(x));sec++;}
  const hsLines=genChecklistLines("人才安居与大湾区境外个税",LASTHS,CN[sec-1]);if(hsLines.length)hsLines.forEach(x=>L.push(x));
  L.push("==================================================");
  L.push("说明：本清单金额为按所填画像的规则估算，仅供申报准备参考，最终条件、标准与时效以官方最新文件及窗口审核为准；办理前建议拨打当地 12345 政务服务便民热线或窗口电话复核。");
  brandTextFoot().forEach(x=>L.push(x));
  return L.join("\n");
}
// 汇总各域命中项可测算金额（就业/留学/企业/安居；落户通道与评审类不计）
function sumMatchedMoney(){
  let s=0;
  const add=it=>{if(!it)return;let v=null;
    if(it.est&&typeof it.est.val==="number")v=it.est.val;
    else if(it.pol&&typeof it.pol.amount_value==="number")v=it.pol.amount_value;
    if(typeof v==="number"&&isFinite(v))s+=v;};
  (LAST.match||[]).forEach(add);(LASTOS.match||[]).forEach(add);
  (LASTENT.match||[]).forEach(add);(LASTHS.match||[]).forEach(add);
  return Math.round(s);
}
// ===== 申报主体 + 自办/顾问模式：按主体显隐业务盒，匹配引擎不改 =====
let SUBJECT="person", MODE="self";
const BOX_DOM={empBox:["employment_startup"],entBox:["enterprise_support","tech_enterprise"],
  hsBox:["housing","gba_tax"],hkBox:["hukou"],osBox:["overseas"]};
const SUBJECT_WANT={person:["empBox","hkBox","hsBox"],unit:["entBox","hsBox"],
  entrepreneur:["empBox"],overseas:["osBox"]};
const SUBJECT_BTN={person:"开始匹配我的政策",unit:"开始评估本企业",entrepreneur:"开始匹配创业政策",overseas:"开始评估留学/海外政策"};
const SUBJECT_HINT={
 person:"个人求职者/毕业生：填就业、落户、人才安居与境外个税，只显示与你相关的项。",
 unit:"企业/用人单位：填用工、社保、研发、残保金，评估稳岗、用工扶持、高企奖补与单位安居。",
 entrepreneur:"自主创业者：填创业与经营情况，匹配创业补贴、创业担保贷款等。",
 overseas:"海外/留学人才：填学历、首次来本地情况，匹配留学生与海外青年人才政策。"};
const SUBJ_LABEL={person:"个人求职者",unit:"企业单位",entrepreneur:"自主创业者",overseas:"海外/留学人才"};
function subjName(v){return SUBJ_LABEL[v]||"";}
function cityDoms(){
  const cv=document.getElementById("citySelect").value;
  const info=(typeof CITY_FIELDS!=="undefined")?CITY_FIELDS[cv]:null;
  if(info)return new Set(info.domains);
  // ★ 还没选城市（空库时下拉无可选项）：用统一字段模板兜底，
  //   让使用者一眼看到引擎能填哪些字段，而不是所有分节都被收起成空白。
  if(!cv&&typeof FIELD_TPL!=="undefined")return new Set(FIELD_TPL.domains||[]);
  return new Set();
}
function boxVisibleByCity(id,doms){
  const need=BOX_DOM[id];if(!need)return true;
  return need.some(d=>doms.has(d));
}
function updateMatchHeader(){
  const cv=document.getElementById("citySelect").value;
  const _csel=document.getElementById("citySelect");
  const nm=(typeof CITY_NAMES!=="undefined"&&CITY_NAMES[cv])||(cv?((_csel&&_csel.selectedOptions&&_csel.selectedOptions[0])?_csel.selectedOptions[0].text:"本市"):"尚未选择城市");
  const titles={
   person:["个人政策匹配 · "+nm,"就业创业补贴、落户、人才住房、境外人才个税：填画像，右侧给可办项、金额、材料与办理路径。"],
   unit:["企业政策匹配 · "+nm,"企业用工扶持、科技企业奖补、单位人才住房、境外人才个税代办：评估可享扶持与金额。"],
   entrepreneur:["创业者政策匹配 · "+nm,"自主创业者：创业补贴、创业担保贷款、场租与带动就业扶持。"],
   overseas:["海外/留学人才政策匹配 · "+nm,"留学生与海外青年人才：生活与就业补贴、安居、创业资助。"]};
  const t=titles[SUBJECT]||titles.person,h1=document.querySelector("header h1"),hp=document.querySelector("header p");
  if(h1)h1.textContent=t[0];if(hp)hp.textContent=t[1];
}
function fieldLevelCity(){
  const cv=document.getElementById("citySelect").value;
  const info=(typeof CITY_FIELDS!=="undefined")?CITY_FIELDS[cv]:null;if(!info)return;
  function fl(boxId,fset){document.querySelectorAll("#"+boxId+" [data-field]").forEach(el=>{
    const box=el.closest(".fld")||el.closest("label.check");if(!box)return;
    box.style.display=fset.has(el.getAttribute("data-field"))?"":"none";});}
  fl("entBox",new Set(info.fields.unit));
  fl("hsBox",new Set(info.fields.person));
}
function renderMatch(){
  const doms=cityDoms(),want=new Set(SUBJECT_WANT[SUBJECT]);
  Object.keys(BOX_DOM).forEach(id=>{
    const e=document.getElementById(id);if(!e)return;
    const vis=want.has(id)&&boxVisibleByCity(id,doms);
    e.style.display=vis?"":"none";if(!vis)e.open=false;
  });
  const tb=document.getElementById("topicBox");if(tb)tb.style.display=(SUBJECT==="overseas")?"none":"";
  const cb=document.getElementById("clientBox"),bb=document.getElementById("brandBox");
  if(cb)cb.style.display="none";
  if(bb)bb.style.display=(MODE==="advisor")?"":"none";
  document.getElementById("view-match").classList.toggle("adv",MODE==="advisor");
  var acn=document.getElementById("advCurName");
  if(acn)acn.textContent=CURRENT_CID?("当前客户："+CLIENTS[CURRENT_CID].name):"未选择客户";
  if(SUBJECT==="person"||SUBJECT==="entrepreneur"){kind=SUBJECT;renderForm();}
  const rb=document.getElementById("runBtn");if(rb)rb.textContent=SUBJECT_BTN[SUBJECT];
  const ht=document.getElementById("roleHint");if(ht)ht.textContent=SUBJECT_HINT[SUBJECT];
  document.querySelectorAll("#subjectSwitch .subjbtn").forEach(b=>b.classList.toggle("active",b.dataset.s===SUBJECT));
  if(SUBJECT==="unit"){var _eb=document.getElementById("entBox");if(_eb)_eb.open=true;}
  updateMatchHeader();fieldLevelCity();renderHkExtra();
}
function applySubject(x){SUBJECT=x;try{localStorage.setItem("sz_subject",x);}catch(e){}renderMatch();}
function setMode(m){MODE=m;try{localStorage.setItem("sz_mode",m);}catch(e){}renderMatch();}
function initSubject(){
  let x="person",m="self";
  try{x=localStorage.getItem("sz_subject")||"person";m=localStorage.getItem("sz_mode")||"self";}catch(e){}
  var VALID={person:1,unit:1,entrepreneur:1,overseas:1};
  if(!VALID[x])x="person";
  if(m!=="advisor")m="self";
  try{localStorage.setItem("sz_subject",x);localStorage.setItem("sz_mode",m);}catch(e){}
  document.querySelectorAll("#subjectSwitch .subjbtn").forEach(b=>b.onclick=function(){applySubject(b.dataset.s);});
  MODE=m;applySubject(x);
}
// ===== 客户档案（本机一户一档）：通用表单快照，与业务域解耦 =====
// 页面内输入/确认/轻提示（不依赖浏览器原生 prompt/confirm/alert，兼容内置webview）
function uiPrompt(title,def,cb){const m=document.getElementById("uiPrompt");document.getElementById("uiPTitle").textContent=title;const i=document.getElementById("uiPInput");i.value=def||"";m.classList.remove("hide");setTimeout(function(){try{i.focus();i.select();}catch(e){}},30);
  const ok=document.getElementById("uiPOk"),cl=document.getElementById("uiPCancel");
  function done(v){m.classList.add("hide");ok.onclick=null;cl.onclick=null;i.onkeydown=null;m.onclick=null;cb(v);}
  ok.onclick=function(){done(i.value);};cl.onclick=function(){done(null);};
  i.onkeydown=function(e){if(e.key==="Enter")done(i.value);else if(e.key==="Escape")done(null);};
  m.onclick=function(e){if(e.target===m)done(null);};}
function uiConfirm(msg,cb){const m=document.getElementById("uiConfirm");document.getElementById("uiCMsg").textContent=msg;m.classList.remove("hide");
  const ok=document.getElementById("uiCOk"),cl=document.getElementById("uiCCancel");
  function done(v){m.classList.add("hide");ok.onclick=null;cl.onclick=null;m.onclick=null;cb(v);}
  ok.onclick=function(){done(true);};cl.onclick=function(){done(false);};
  m.onclick=function(e){if(e.target===m)done(false);};}
let _toastTimer=null;
function toast(msg){const t=document.getElementById("uiToast");if(!t)return;t.textContent=msg;t.style.display="block";clearTimeout(_toastTimer);_toastTimer=setTimeout(function(){t.style.display="none";},2600);}
let CLIENTS={},CURRENT_CID=null;
function clLoad(){try{const x=localStorage.getItem("sz_clients_v1");if(x)CLIENTS=JSON.parse(x)||{};}catch(e){CLIENTS={};}}
function clPersist(){try{localStorage.setItem("sz_clients_v1",JSON.stringify(CLIENTS));}catch(e){toast("本机浏览器存储不可用，档案未能保存，可用导出清单留底。");}}
function formSnapshot(){const out={};document.querySelectorAll("input,select,textarea").forEach(el=>{if(!el.id)return;if(el.id.indexOf("br_")===0||el.id==="cl_search")return;if(["file","button","submit","reset"].indexOf(el.type)>=0)return;if(el.type==="checkbox")out[el.id]=el.checked?"1":"";else if(el.type==="radio"){if(el.checked)out[el.id]=el.value;}else out[el.id]=el.value;});return out;}
function restoreSnapshot(snap){document.querySelectorAll("input,select,textarea").forEach(el=>{if(!el.id||!(el.id in snap))return;const v=snap[el.id];if(el.type==="checkbox")el.checked=(v==="1");else if(el.type==="radio")el.checked=(el.value===v);else{el.value=v;if(el.tagName==="SELECT"){el.dispatchEvent(new Event("change"));}}});}
function clSummaryText(){const r=window.LAST_RUN;if(!r)return "尚未测算";return "可办 "+r.total+" 项 · 差一点 "+r.near+" 项"+(r.money>0?(" · 可测算约 ¥"+Number(r.money).toLocaleString()):"")+" · "+r.ts;}
function fillCnCity(){
  var sel=document.getElementById("cn_city");if(sel.options.length)return;var h="";
  Object.keys(CITY_FIELDS).forEach(code=>{var nm=(typeof CITY_NAMES!=="undefined"&&CITY_NAMES[code])?CITY_NAMES[code]:code;h+='<option value="'+code+'">'+nm+'</option>';});
  sel.innerHTML=h;
}
function openNewClient(){
  if(typeof closeWb==="function")closeWb();
  fillCnCity();
  document.getElementById("cn_name").value="";document.getElementById("cn_contact").value="";
  document.getElementById("cn_city").value=document.getElementById("citySelect").value;
  document.getElementById("cn_subject").value=SUBJECT;
  document.getElementById("clNewMask").classList.remove("hide");
  setTimeout(function(){try{document.getElementById("cn_name").focus();}catch(e){}},30);
}
function closeNewClient(){document.getElementById("clNewMask").classList.add("hide");}
function doNewClient(){
  var name=document.getElementById("cn_name").value.trim();
  if(!name){toast("请填写客户名称");return;}
  var id="c"+Date.now();
  CLIENTS[id]={id:id,name:name,contact:document.getElementById("cn_contact").value.trim(),
    city:document.getElementById("cn_city").value,subject:document.getElementById("cn_subject").value,
    snap:{},summary:"尚未体检",status:"new",created:new Date().toLocaleString(),updated:new Date().toLocaleString()};
  clPersist();CURRENT_CID=id;renderClientList();if(typeof renderWorkbench==="function")renderWorkbench();closeNewClient();
  toast("已建立客户档案："+name);
}
function saveNewClient(){openNewClient();}
function updateClient(id){const c=CLIENTS[id||CURRENT_CID];if(!c){saveNewClient();return;}c.snap=formSnapshot();c.summary=clSummaryText();c.updated=new Date().toLocaleString();clPersist();renderClientList();}
function loadClient(id){const c=CLIENTS[id];if(!c)return;
  CURRENT_CID=id;
  if(c.city){var cs=document.getElementById("citySelect");cs.value=c.city;cs.dispatchEvent(new Event('change'));}
  if(c.subject)applySubject(c.subject);
  restoreSnapshot(c.snap);renderClientList();run();}
function clientChecklist(id){const c=CLIENTS[id];if(!c)return;restoreSnapshot(c.snap);CURRENT_CID=id;renderClientList();(async()=>{await run();openChecklist();})();}
function renameClient(id){const c=CLIENTS[id];if(!c)return;uiPrompt("修改客户名称：",c.name,function(n){n=(n||"").trim();if(!n)return;c.name=n;clPersist();renderClientList();if(typeof renderWorkbench==="function")renderWorkbench();});}
function delClient(id){const c=CLIENTS[id];if(!c)return;uiConfirm("删除客户「"+c.name+"」？此操作不可恢复。",function(ok){if(!ok)return;delete CLIENTS[id];if(CURRENT_CID===id)CURRENT_CID=null;clPersist();renderClientList();if(typeof renderWorkbench==="function")renderWorkbench();toast("已删除客户："+c.name);});}
const CL_ACTS={load:loadClient,cl:clientChecklist,upd:updateClient,ren:renameClient,del:delClient};
function renderClientList(){const box=document.getElementById("clientList");if(!box)return;const q=((document.getElementById("cl_search")||{}).value||"").trim();let ids=Object.keys(CLIENTS).sort((a,b)=>String(CLIENTS[b].updated).localeCompare(String(CLIENTS[a].updated)));let h="";
  ids.forEach(id=>{const c=CLIENTS[id];if(q&&c.name.indexOf(q)<0)return;const cur=id===CURRENT_CID;
    h+='<div class="clitem'+(cur?" cur":"")+'"><div class="cn">'+esc(c.name)+(cur?' <span class="curtag">当前</span>':"")+'</div><div class="cs">'+esc(c.summary||"")+'</div><div class="ca">'
      +'<div class="cm2" style="font-size:11px;color:#718096;margin:2px 0;">'+(c.contact?esc(c.contact)+' · ':"")+esc(subjName(c.subject))+'</div>'
      +'<a data-act="load" data-id="'+id+'">调阅重算</a><a data-act="cl" data-id="'+id+'">出清单</a><a data-act="upd" data-id="'+id+'">更新</a><a data-act="ren" data-id="'+id+'">改名</a><a data-act="del" data-id="'+id+'">删除</a></div></div>';});
  box.innerHTML=h||'<div class="cempty">还没有客户档案。左侧填好画像并点「开始匹配」后，点「存为新客户」即可建立一户一档。</div>';
  box.querySelectorAll("a[data-act]").forEach(a=>{a.onclick=()=>{const f=CL_ACTS[a.dataset.act];if(f)f(a.dataset.id);};});
  if(typeof renderAdvList==="function")renderAdvList();}
function renderAdvList(){
  var box=document.getElementById("advClientList");if(!box)return;
  var q=((document.getElementById("advSearch")||{}).value||"").trim();
  var stf=((document.getElementById("advFilter")||{}).value||"");
  var fsel=document.getElementById("advFilter");
  if(fsel&&!fsel.options.length){fsel.innerHTML='<option value="">全部状态</option>'+CL_STATUS.map(function(x){return '<option value="'+x[0]+'">'+x[1]+'</option>';}).join("");}
  var today=new Date().toISOString().slice(0,10);
  var ids=Object.keys(CLIENTS).sort(function(a,b){return (Number(CLIENTS[b].money||0))-(Number(CLIENTS[a].money||0));}),h="";
  ids.forEach(function(id){var c=CLIENTS[id];
    if(q&&c.name.indexOf(q)<0)return;
    var cs=STATUS_MIGRATE[c.status]||c.status||"new";
    if(stf&&cs!==stf)return;
    var cur=id===CURRENT_CID;
    var due=(c.followup&&c.followup<=today&&cs!=="deal");
    var moneyTxt=c.money?('<div class="ac" style="color:#1F7A3A;font-weight:600;">可测算约 ¥'+Number(c.money).toLocaleString()+'</div>'):'';
    var dueTag=due?'<span style="display:inline-block;margin-left:6px;padding:1px 7px;background:#C0392B;color:#fff;border-radius:8px;font-size:11px;">到期跟进</span>':'';
    h+='<div class="aitem'+(cur?' cur':'')+(due?' style="border-left:3px solid #C0392B;"':'')+'" data-id="'+id+'">'
      +'<div class="an">'+esc(c.name)+dueTag+'</div>'
      +'<div class="ac">'+(c.contact?esc(c.contact)+' · ':"")+esc(subjName(c.subject))+'</div>'
      +moneyTxt
      +'<div class="as">'+esc(clStatusName(c.status))+' · '+esc(c.summary||"尚未体检")+'</div>'
      +'<div class="ao"><a data-a="cl" data-id="'+id+'">出清单</a><a data-a="del" data-id="'+id+'">删除</a></div></div>';
  });
  box.innerHTML=h||'<div class="aempty">还没有客户，点上方「新建客户」开始。</div>';
  box.querySelectorAll(".aitem").forEach(function(el){el.onclick=function(e){if(e.target.tagName==='A')return;loadClient(el.dataset.id);};});
  box.querySelectorAll("a[data-a]").forEach(function(a){a.onclick=function(e){e.stopPropagation();var id=a.dataset.id;if(a.dataset.a==='cl')clientChecklist(id);else delClient(id);};});
}
// ===== 顾问工作台（弹窗版，保留供批量重算/导出入口） =====
const CL_STATUS=[["new","新线索"],["talked","已沟通"],["pay","待付费"],["deal","已成交"],["hold","暂缓/流失"]];
const STATUS_MIGRATE={plan:"talked",apply:"talked",done:"deal"}; // 兼容旧申报口径状态
function clStatusName(v){v=STATUS_MIGRATE[v]||v;const f=CL_STATUS.find(x=>x[0]===v);return f?f[1]:"新线索";}
function openWb(){renderWorkbench();document.getElementById("wbMask").classList.remove("hide");}
function closeWb(){document.getElementById("wbMask").classList.add("hide");}
function wbSet(id,k,v){const c=CLIENTS[id];if(!c)return;c[k]=v;c.updated=new Date().toLocaleString();clPersist();if(k==="status"||k==="followup")renderWbStat();}
function renderWbStat(){const ids=Object.keys(CLIENTS);let follow=0,money=0,total=0;ids.forEach(id=>{const c=CLIENTS[id];money+=Number(c.money||0);total+=Number(c.total||0);const t=c.followup;const _cs=STATUS_MIGRATE[c.status]||c.status;if(t&&t<=new Date().toISOString().slice(0,10)&&_cs!=="deal")follow++;});const el=document.getElementById("wbStat");if(el)el.innerHTML="客户 <b>"+ids.length+"</b> 户 · 在办可办事项合计 <b>"+total+"</b> 项 · 可测算金额合计约 <b>¥"+money.toLocaleString()+"</b> · 到期/逾期跟进 <b style='color:#C0392B'>"+follow+"</b> 户（金额为规则估算，以官方审核为准）";}
function renderWorkbench(){const box=document.getElementById("wbBody");if(!box)return;const ids=Object.keys(CLIENTS).sort((a,b)=>String(CLIENTS[b].updated).localeCompare(String(CLIENTS[a].updated)));
  if(!ids.length){box.innerHTML='<div class="cempty">还没有客户。先在左侧建档，再回到这里管理。</div>';renderWbStat();return;}
  let h='<table style="width:100%;border-collapse:collapse;font-size:12px;"><thead><tr style="background:#F2F6FB;text-align:left;">'
    +'<th style="padding:6px 8px;border-bottom:1px solid #E4E3DD;">客户</th><th style="padding:6px 8px;border-bottom:1px solid #E4E3DD;">最近结论</th><th style="padding:6px 8px;border-bottom:1px solid #E4E3DD;">状态</th><th style="padding:6px 8px;border-bottom:1px solid #E4E3DD;">跟进日期</th><th style="padding:6px 8px;border-bottom:1px solid #E4E3DD;">备注</th><th style="padding:6px 8px;border-bottom:1px solid #E4E3DD;">操作</th></tr></thead><tbody>';
  ids.forEach(id=>{const c=CLIENTS[id];
    const sopts=CL_STATUS.map(x=>'<option value="'+x[0]+'"'+(x[0]===(STATUS_MIGRATE[c.status]||c.status||"new")?" selected":"")+'>'+x[1]+'</option>').join("");
    h+='<tr style="border-bottom:1px solid #EEF1F5;"><td style="padding:6px 8px;font-weight:600;white-space:nowrap;">'+esc(c.name)+'<div style="font-weight:400;font-size:11px;color:#718096;">'+(c.contact?esc(c.contact)+' · ':"")+esc(subjName(c.subject))+'</div></td>'
      +'<td style="padding:6px 8px;color:#4A5568;min-width:180px;">'+esc(c.summary||"尚未测算")+'</td>'
      +'<td style="padding:6px 8px;"><select data-id="'+id+'" data-k="status" style="font-size:12px;padding:3px;">'+sopts+'</select></td>'
      +'<td style="padding:6px 8px;"><input type="date" data-id="'+id+'" data-k="followup" value="'+esc(c.followup||"")+'" style="font-size:12px;padding:3px;"></td>'
      +'<td style="padding:6px 8px;"><input type="text" data-id="'+id+'" data-k="note" value="'+esc(c.note||"")+'" placeholder="跟进备注" style="font-size:12px;padding:3px;width:130px;"></td>'
      +'<td style="padding:6px 8px;white-space:nowrap;"><a data-wb="load" data-id="'+id+'" style="color:#2B6CB0;cursor:pointer;margin-right:8px;">调阅</a><a data-wb="cl" data-id="'+id+'" style="color:#2B6CB0;cursor:pointer;margin-right:8px;">清单</a><a data-wb="del" data-id="'+id+'" style="color:#C0392B;cursor:pointer;">删除</a></td></tr>';});
  h+='</tbody></table>';box.innerHTML=h;
  box.querySelectorAll("select[data-k],input[data-k]").forEach(el=>{el.onchange=()=>wbSet(el.dataset.id,el.dataset.k,el.value);});
  box.querySelectorAll("a[data-wb]").forEach(a=>a.onclick=()=>{const id=a.dataset.id;if(a.dataset.wb==="load"){closeWb();loadClient(id);}else if(a.dataset.wb==="cl"){closeWb();clientChecklist(id);}else delClient(id);});
  renderWbStat();}
async function recomputeOne(id){const c=CLIENTS[id];if(!c)return;const curSnap=formSnapshot();restoreSnapshot(c.snap);
  // ★ 批量重算也必须带 city（同 run() 的 _injectCity）：引擎没有默认城市。
  const _cy=(document.getElementById("citySelect")||{}).value||"";
  const _wc=pr=>{if(_cy&&pr)pr.city=_cy;return pr;};
  const tasks=[apiMatch(_wc(collect()))];
  const hk=collectHk();if(hk.has)tasks.push(apiMatch(_wc(hk.p)));
  const os=collectOs();if(os.has)tasks.push(apiMatch(_wc(os.p)));
  const en=collectEnt();if(en.has)tasks.push(apiMatch(_wc(en.p)));
  const hs=collectHs();if(hs.has)tasks.push(apiMatch(_wc(hs.p)));
  let total=0,near=0,money=0;
  try{const rs=await Promise.all(tasks);
    rs.forEach(j=>{const D=j.domains||{};Object.keys(D).forEach(k=>{const d=D[k];if(!d)return;if(k==="hukou"){(d.decisions||[]).forEach(x=>{if(x.status==="eligible")total++;else if(x.status==="near")near++;});}else{total+=(d.match||[]).length;near+=(d.near||[]).length;(d.match||[]).forEach(x=>{if(typeof x.amount_value==="number")money+=x.amount_value;});}});});
  }catch(e){restoreSnapshot(curSnap);throw e;}
  restoreSnapshot(curSnap);
  c.total=total;c.near=near;c.money=Math.round(money);
  c.summary="可办 "+total+" 项 · 差一点 "+near+" 项"+(money>0?(" · 可测算约 ¥"+Math.round(money).toLocaleString()):"")+" · "+new Date().toLocaleString();
  c.updated=new Date().toLocaleString();}
async function recomputeAll(){const btn=document.getElementById("wbRecompute");const ids=Object.keys(CLIENTS);if(!ids.length){toast("还没有客户，请先建档。");return;}btn.disabled=true;
  for(let i=0;i<ids.length;i++){btn.textContent="重算中 "+(i+1)+"/"+ids.length;try{await recomputeOne(ids[i]);}catch(e){btn.disabled=false;btn.textContent="🔄 批量重算全部";toast("客户 "+CLIENTS[ids[i]].name+" 重算失败："+e.message);return;}}
  clPersist();btn.disabled=false;btn.textContent="🔄 批量重算全部";renderClientList();renderWorkbench();toast("全部客户已重算完成");}
function exportClientsCsv(){const ids=Object.keys(CLIENTS);if(!ids.length){toast("还没有客户，请先建档。");return;}
  const row=a=>a.map(v=>{v=String(v==null?"":v);return /[",\n]/.test(v)?('"'+v.replace(/"/g,'""')+'"'):v;}).join(",");
  const L=[row(["客户名称","联系方式","城市","申报主体","状态","跟进日期","可办项数","差一点项数","可测算金额(元)","备注","最近结论","创建时间","更新时间"])];
  ids.forEach(id=>{const c=CLIENTS[id];L.push(row([c.name,c.contact||"",c.city||"",subjName(c.subject),clStatusName(c.status||"new"),c.followup||"",c.total||"",c.near||"",c.money||"",c.note||"",c.summary||"",c.created||"",c.updated||""]));});
  const blob=new Blob(["\ufeff"+L.join("\n")],{type:"text/csv;charset=utf-8"}),a=document.createElement("a");
  a.href=URL.createObjectURL(blob);a.download="客户档案总表.csv";document.body.appendChild(a);a.click();setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove();},600);}
function initWorkbench(){const o=document.getElementById("wbOpenBtn");if(o)o.onclick=openWb;const c=document.getElementById("wbClose");if(c)c.onclick=closeWb;const r=document.getElementById("wbRecompute");if(r)r.onclick=recomputeAll;const x=document.getElementById("wbCsv");if(x)x.onclick=exportClientsCsv;const m=document.getElementById("wbMask");if(m)m.onclick=e=>{if(e.target.id==="wbMask")closeWb();};}
function initClients(){clLoad();const s=document.getElementById("saveClientBtn");if(s)s.onclick=saveNewClient;const u=document.getElementById("updClientBtn");if(u)u.onclick=()=>updateClient(CURRENT_CID);const q=document.getElementById("cl_search");if(q)q.oninput=renderClientList;renderClientList();initWorkbench();
  ["clNewOk"].forEach(i=>{var e=document.getElementById(i);if(e)e.onclick=doNewClient;});
  ["clNewCancel","clNewCancel2"].forEach(i=>{var e=document.getElementById(i);if(e)e.onclick=closeNewClient;});
  var nm=document.getElementById("clNewMask");if(nm)nm.onclick=function(e){if(e.target===nm)closeNewClient();};
  [["advNew",openNewClient],["advExit",function(){setMode('self');}],["advCsv",exportClientsCsv],["advRecompute",recomputeAll],
   ["advSave",saveNewClient],["advUpd",function(){updateClient(CURRENT_CID);}],["advCl",openChecklist]]
   .forEach(function(pair){var e=document.getElementById(pair[0]);if(e)e.onclick=pair[1];});
  var as0=document.getElementById("advSearch");if(as0)as0.oninput=renderAdvList;
  var af0=document.getElementById("advFilter");if(af0)af0.onchange=renderAdvList;
}
function hasList(){return (LAST.p&&LAST.match.length>0)||LASTHK.eligible.length>0||LASTOS.match.length>0||LASTENT.match.length>0||LASTHS.match.length>0;}
function openChecklist(){
  if(!hasList()){alert("请先在左侧填写任一块画像（就业 / 落户 / 留学 / 企业扶持 / 安居境外个税，可只填一块）并点「开始匹配」，出现可办事项后再生成申报清单。");return;}
  refreshChecklist();document.getElementById("clMask").classList.remove("hide");
}
function refreshChecklist(){document.getElementById("clText").textContent=checklistText();}
function closeChecklist(){document.getElementById("clMask").classList.add("hide");}
function fallbackCopy(txt,ok){
  const ta=document.createElement("textarea");ta.value=txt;ta.style.position="fixed";ta.style.opacity="0";document.body.appendChild(ta);ta.focus();ta.select();
  try{document.execCommand("copy");ok&&ok();}catch(e){alert("自动复制失败，请在清单内手动全选复制。");}
  document.body.removeChild(ta);
}
function copyChecklist(){
  if(!hasList()){alert("当前没有可申领补贴，请先在左侧填写并点「开始匹配」。");return;}
  const txt=checklistText(),btn=document.getElementById("copyCl"),old=btn.textContent;
  const done=()=>{btn.textContent="已复制 ✓";setTimeout(()=>btn.textContent=old,1600);};
  if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(txt).then(done).catch(()=>fallbackCopy(txt,done));}
  else fallbackCopy(txt,done);
}
function downloadChecklist(){
  if(!hasList()){alert("当前没有可申领补贴，请先在左侧填写并点「开始匹配」。");return;}
  const safe=String(checklistText()).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
  const html='<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>政策申报清单</title>'
    +'<style>body{font-family:"Microsoft YaHei",Arial,sans-serif;padding:30px;color:#1A1B1C;line-height:1.7;font-size:13px;}h1{font-size:18px;margin-bottom:4px;}.nop{margin-bottom:14px;}pre{white-space:pre-wrap;word-break:break-word;font-family:inherit;}@media print{.nop{display:none;}body{padding:0;}}</style></head><body>'
    +'<div class="nop"><button onclick="window.print()" style="padding:8px 18px;background:#2B6CB0;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:13px;">打印 / 另存为 PDF</button>　<span style="color:#6B7280;font-size:12px;">也可直接 Ctrl+S 保存本页</span></div>'
    +brandHtmlHead()
    +'<h1>就业创业补贴 · 个性化申报清单</h1><pre>'+safe+'</pre>'
    +(BRAND.qr?('<div style="text-align:right;margin-top:12px;"><img src="'+BRAND.qr+'" style="max-width:140px;max-height:140px;border:1px solid #ddd;"/><div style="font-size:11px;color:#6B7280;margin-top:2px;">扫码咨询'+(BRAND.advisor?(" · "+esc(BRAND.advisor)):"")+'</div></div>'):"")
    +'</body></html>';
  const blob=new Blob([html],{type:"text/html;charset=utf-8"}),a=document.createElement("a");
  a.href=URL.createObjectURL(blob);a.download="政策个性化申报清单.html";document.body.appendChild(a);a.click();
  setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove();},800);
}
// 下载 Excel 清单：调服务端 /api/v1/export/checklist 生成 xlsx（20 列 + 按城市速览）。
// ★ 与上面的「下载/打印」区别：那个导的是 HTML，客户拿到还要自己转格式；
//   这个直接给 .xlsx，中介可以原样转发给企业客户。生成逻辑全部在服务端，
//   前端只负责取 blob 落地 —— 列定义不在浏览器里复制第二份。
async function downloadChecklistXlsx(){
  if(!LAST.p){alert("当前没有可申领补贴，请先在左侧填写并点「开始匹配」。");return;}
  const btn=document.getElementById("dlXlsx");
  if(btn&&btn.disabled)return;
  const old=btn?btn.textContent:"";
  if(btn){btn.textContent="生成中…";btn.disabled=true;}
  try{
    const r=await fetch(API_BASE+"/api/v1/export/checklist",{
      method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({profile:LAST.p})});
    if(!r.ok){
      let msg="导出失败（HTTP "+r.status+"）";
      try{const j=await r.json();if(j&&j.detail)msg=j.detail;}catch(e){}
      throw new Error(msg);
    }
    const blob=await r.blob();
    const nm=((CITY_NAMES&&CITY_NAMES[LAST.p.city])||"政策")+"可申报清单.xlsx";
    const a=document.createElement("a");
    a.href=URL.createObjectURL(blob);a.download=nm;
    document.body.appendChild(a);a.click();
    setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove();},800);
  }catch(e){
    alert("导出 Excel 失败："+e.message+"\n（若已部署为纯静态页，需同时启动后端服务）");
  }finally{
    if(btn){btn.textContent=old;btn.disabled=false;}
  }
}
function buildChecklistDoc(safe){
  return '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><title>政策个性化申报清单</title>'
    +'<style>@page{size:A4;margin:16mm 14mm;}body{font-family:"Microsoft YaHei",Arial,sans-serif;padding:28px;color:#1A1B1C;line-height:1.65;font-size:12.5px;}h1{font-size:18px;margin:6px 0 2px;}.sub{font-size:11.5px;color:#6B7280;margin-bottom:12px;}pre{white-space:pre-wrap;word-break:break-word;font-family:inherit;}.nop{margin-bottom:14px;}.brand{margin-bottom:10px;}@media print{.nop{display:none;}body{padding:0;}pre{break-inside:auto;}}</style></head><body>'
    +'<div class="nop"><button onclick="window.print()" style="padding:9px 20px;background:#2B6CB0;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:13px;">打印 / 另存为 PDF</button>&nbsp;<span style="color:#6B7280;font-size:12px;">在打印目标里选“另存为 PDF”即可导出；也可 Ctrl+S 保存本页</span></div>'
    +brandHtmlHead()
    +'<h1>政策匹配 · 个性化申报清单</h1><div class="sub">就业创业 / 落户 / 留学人才 / 企业扶持 / 人才安居 / 境外个税　数据版本 '+esc(DATA_VERSION||"")+'</div><pre>'+safe+'</pre>'
    +(BRAND.qr?('<div style="text-align:right;margin-top:12px;"><img src="'+BRAND.qr+'" style="max-width:130px;max-height:130px;border:1px solid #ddd;"/><div style="font-size:11px;color:#6B7280;margin-top:2px;">扫码咨询'+(BRAND.advisor?(" · "+esc(BRAND.advisor)):"")+'</div></div>'):"")
    +'</body></html>';
}
function vtLookupHtml(){
  return '<div id="vtBox" style="border:1px solid #D5DEEA;border-radius:10px;padding:12px;margin:8px 0;background:#F7FAFD;">'
    +'<div style="font-weight:600;font-size:14px;margin-bottom:8px;">🔍 工种补贴速查（选工种+等级，立即查能补多少）</div>'
    +'<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end;">'
    +'<div><label style="font-size:12px;color:#6B7280;">工种类型</label><select id="vtCat" style="margin-top:2px;padding:6px;">'
    +'<option value="B">职业技能等级（B类）</option><option value="D">数字技术工程师</option><option value="S">专项职业能力</option></select></div>'
    +'<div id="vtJobWrap"><label style="font-size:12px;color:#6B7280;">工种</label><select id="vtJob" style="margin-top:2px;padding:6px;min-width:160px;"></select></div>'
    +'<div id="vtLevelWrap"><label style="font-size:12px;color:#6B7280;">等级</label><select id="vtLevel" style="margin-top:2px;padding:6px;"></select></div>'
    +'</div>'
    +'<div id="vtResult" style="margin-top:10px;font-size:14px;color:#22784C;font-weight:600;">请选择工种与等级…</div>'
    +'<div style="font-size:11px;color:#6B7280;margin-top:4px;" id="vtSrc"></div>'
    +'</div>';
}
var VT_CAT=null;
async function vtLoad(){
  try{
    const city=document.getElementById("citySelect").value;
    VT_CAT=await (await fetch('/api/v1/vt_catalog?city='+city)).json();
    vtBuildCat();
  }catch(e){document.getElementById("vtResult").innerText="目录加载失败";}
}
function vtBuildCat(){
  if(!VT_CAT||!VT_CAT.available){
    // 该城没有工种目录（很常见）⇒ 整块速查器收起，不留「暂未收录」的空壳
    var box=document.getElementById("vtBox");if(box)box.style.display="none";
    return;
  }
  const cat=document.getElementById("vtCat");
  const job=document.getElementById("vtJob");
  const lv=document.getElementById("vtLevel");
  function setJobOptions(list, withLevel){
    job.innerHTML=list.map(j=>'<option value="'+j.v+'">'+j.t+'</option>').join("");
    lv.innerHTML="";
    if(withLevel){Object.keys(VT_CAT.level_names).forEach(k=>lv.add(new Option(VT_CAT.level_names[k],k)));}
    lv.parentElement.style.display=withLevel?"block":"none";
    vtCalc();
  }
  cat.onchange=()=>vtBuildCat();
  job.onchange=vtCalc; lv.onchange=vtCalc;
  if(cat.value==="B"){
    setJobOptions(VT_CAT.B_confirmed.map(b=>({v:b.name,t:b.name})),true);
  }else if(cat.value==="D"){
    const dg=VT_CAT.digital_engineer;
    setJobOptions((dg.representative_jobs||[]).map(j=>({v:j,t:j})),false);
    lv.innerHTML='<option value="junior">初级</option><option value="mid">中级</option><option value="senior">高级</option>';
    lv.parentElement.style.display="block";
  }else{
    const sp=VT_CAT.special_ability;
    setJobOptions((sp.confirmed_items_800||[]).map(j=>({v:j,t:j})),false);
  }
  vtCalc();
}
function vtCalc(){
  if(!VT_CAT||!VT_CAT.available)return;
  const cat=document.getElementById("vtCat").value;
  const job=document.getElementById("vtJob").value;
  const lv=document.getElementById("vtLevel").value;
  const res=document.getElementById("vtResult");
  const src=document.getElementById("vtSrc");
  let amt=null,note="";
  if(cat==="B"){
    const b=VT_CAT.B_confirmed.find(x=>x.name===job);
    if(b&&b.levels[lv]!=null){amt=b.levels[lv];note="按广东省职业技能培训补贴目录，"+job+"（"+VT_CAT.level_names[lv]+"）";}
  }else if(cat==="D"){
    const la=VT_CAT.digital_engineer.levels_amount||{};
    if(la[lv]!=null){amt=la[lv];note="数字技术工程师培训（"+job+"）";}
  }else{
    const sp=VT_CAT.special_ability;
    amt=sp.amount_mostly;note="专项职业能力（"+job+"），常见 "+sp.range+" 元";
  }
  if(amt!=null){res.innerHTML='✅ 可申领补贴约 <b style="font-size:18px;">¥'+Number(amt).toLocaleString()+'</b>';src.innerText=(VT_CAT.source_note||"").slice(0,90);}
  else{res.innerText="该工种金额待官方目录确认";}
}
function printChecklist(){
  if(!hasList()){alert("当前没有可申领事项，请先在左侧填写并点「开始匹配」。");return;}
  refreshChecklist();
  const safe=String(checklistText()).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
  const w=window.open("","_blank");
  if(!w){alert("浏览器拦截了打印窗口，请允许本站弹窗后重试（或用“下载/打印”）。");return;}
  w.document.open();w.document.write(buildChecklistDoc(safe));w.document.close();
  w.focus();setTimeout(()=>{try{w.print();}catch(e){}},350);
}
function quickRun(){
  var sc=document.getElementById('qScale').value;
  var st=document.getElementById('qStaff').value;
  var ui=document.getElementById('qUi').value;
  document.getElementById('en_scale').value=sc;
  document.getElementById('en_staff').value=st;
  if(ui==='yes'){
    document.getElementById('en_paidmonths').value=12;
    document.getElementById('en_notzombie').checked=true;
  }else{
    document.getElementById('en_paidmonths').value=0;
    document.getElementById('en_notzombie').checked=false;
  }
  document.getElementById('qTip').style.display='block';
  run();
}
document.getElementById('qRun').onclick=quickRun;
async function run(){
  const p=collect();
  const _city=document.getElementById("citySelect").value;
  const _cs=document.getElementById("citySelect");
  const _cityName=CITY_NAMES[_city]||((_cs&&_cs.selectedOptions&&_cs.selectedOptions[0])?_cs.selectedOptions[0].text:"本市");
  document.getElementById("cityLabel").textContent="当前匹配"+_cityName+"政策";
  const _tf=FORM[p.kind].tags.field||"identities";
  const empFilled=((p[_tf]&&p[_tf].length>0)||FORM[p.kind].nums.some(n=>Number(p[n[0]])>0)||FORM[p.kind].bools.some(b=>!!p[b[0]]));
  const hkR=collectHk(), osR=collectOs(); OS_P=osR.p;
  const entR=collectEnt(), hsR=collectHs(); LASTENT.p=entR.has?entR.p:null; LASTHS.p=hsR.has?hsR.p:null;
  // ★ 无条件注入 city：引擎没有「默认城市」了，不传就读不到数据。
  //   旧版这里写的是 `_city!=="SZ"`（当时 SZ 是引擎默认城）—— 留着它会让 SZ 城永远 0 条。
  const _injectCity=(prof)=>{if(_city&&prof)prof.city=_city;return prof;};
  _injectCity(p);_injectCity(hkR.p);_injectCity(osR.p);_injectCity(entR.p);_injectCity(hsR.p);
  const jobs=[];
  if(empFilled)jobs.push(["emp",apiMatch(p)]);
  if(hkR.has)jobs.push(["hk",apiMatch(hkR.p)]);
  if(osR.has)jobs.push(["os",apiMatch(osR.p)]);
  if(entR.has)jobs.push(["ent",apiMatch(entR.p)]);
  if(hsR.has)jobs.push(["hs",apiMatch(hsR.p)]);
  let empDom=null,hkDom=null,osDom=null,entEsDom=null,entTcDom=null,hsHsDom=null,hsGbaDom=null,vtDom=null;
  if(jobs.length){
    try{const rs=await Promise.all(jobs.map(j=>j[1]));
      jobs.forEach((j,i)=>{const D=rs[i].domains;if(j[0]==="emp"){empDom=D.employment_startup;vtDom=D.vocational_training;}else if(j[0]==="hk")hkDom=D.hukou;else if(j[0]==="os")osDom=D.overseas;else if(j[0]==="ent"){entEsDom=D.enterprise_support;entTcDom=D.tech_enterprise;}else if(j[0]==="hs"){hsHsDom=D.housing;hsGbaDom=D.gba_tax;}});
    }catch(e){alert("匹配接口调用失败："+e.message+"\n请确认后端已启动：python -m uvicorn server.app:app --port 8000");return;}
  }
  const boxes={match:[],near:[],exited:[]};
  if(empFilled&&empDom){
    (empDom.match||[]).forEach(pol=>{boxes.match.push(polCard(pol,p,{st:"match",fails:[]}));});
    (empDom.near||[]).forEach(pol=>boxes.near.push(polCard(pol,p,{st:"near",fails:pol.missing||[]})));
    (empDom.exited_or_renamed||[]).forEach(pol=>boxes.exited.push(polCard(pol,p,{st:"match",fails:[]})));
  }
  var vtMatchArr=[],vtNearArr=[];
  if(vtDom){
    (vtDom.match||[]).forEach(pol=>{vtMatchArr.push(polCard(pol,p,{st:"match",fails:[]}));});
    (vtDom.near||[]).forEach(pol=>vtNearArr.push(polCard(pol,p,{st:"near",fails:pol.missing||[]})));
  }
  const empMatch=((empFilled&&empDom)?empDom.match||[]:[]);
  const vtMatch=(vtDom?(vtDom.match||[]):[]);
  const matchItems=empMatch.concat(vtMatch).filter(pol=>!voff(pol.valid)).map(pol=>({pol:pol,est:estimate(p,pol.amount)}));
  LAST={p:empFilled?p:null,match:matchItems,nearN:boxes.near.length};
  const hkOut=hkR.has?runHk(hkDom):(LASTHK={eligible:[],near:[],p:null},"");
  const osOut=osR.has?runOs(osDom):(LASTOS={match:[],near:0,p:null},"");
  const entOut=entR.has?runEnt(entEsDom,entTcDom):(LASTENT={match:[],near:0,p:null},"");
  const hsOut=hsR.has?runHs(hsHsDom,hsGbaDom):(LASTHS={match:[],near:0,p:null},"");
  const hkN=LASTHK.eligible.length, osN=LASTOS.match.length, entN=LASTENT.match.length, hsN=LASTHS.match.length, totalN=matchItems.length+hkN+osN+entN+hsN;
  const stParts=[];
  if(empFilled)stParts.push("就业创业 完全符合 <b style='color:#22784C'>"+(empDom?(empDom.match||[]).length:0)+"</b> 项 · 差一点 <b style='color:#8A5A00'>"+boxes.near.length+"</b> 项");
  if(vtDom){var vtN=vtMatchArr.length;var vtNear=vtNearArr.length;if(vtN||vtNear)stParts.push("技能培训 符合 <b style='color:#22784C'>"+vtN+"</b> 项 · 差一点 <b style='color:#8A5A00'>"+vtNear+"</b> 项");}
  if(LASTHK.p)stParts.push("落户 可走 <b style='color:#22784C'>"+hkN+"</b> 条 · 差一点 <b style='color:#8A5A00'>"+LASTHK.near.length+"</b> 条");
  if(LASTOS.p)stParts.push("留学/青年人才 符合 <b style='color:#22784C'>"+osN+"</b> 项 · 差一点 <b style='color:#8A5A00'>"+LASTOS.near+"</b> 项");
  if(LASTENT.p)stParts.push("企业扶持(用工+高企) 符合 <b style='color:#22784C'>"+entN+"</b> 项 · 差一点 <b style='color:#8A5A00'>"+LASTENT.near+"</b> 项");
  if(LASTHS.p)stParts.push("安居/境外个税 符合 <b style='color:#22784C'>"+hsN+"</b> 项 · 差一点 <b style='color:#8A5A00'>"+LASTHS.near+"</b> 项");
  document.getElementById("stat").innerHTML=(stParts.join("　·　")||"请先在左侧填写任一画像（就业 / 落户 / 留学，可只填一个）。")+(DATA_VERSION?("　<span style=\'color:#6B7280;\'>数据版本 "+DATA_VERSION+"</span>"):"");
  const nearTotal=boxes.near.length+LASTHK.near.length+(LASTOS.near||0)+(LASTENT.near||0)+(LASTHS.near||0);
  const moneySum=sumMatchedMoney();
  const chip=(lab,nn)=>nn?('<span class="ovchip">'+lab+' '+nn+'</span>'):"";
  const chipsTxt=chip("就业",matchItems.length)+chip("落户",hkN)+chip("留学人才",osN)+chip("企业扶持",entN)+chip("安居/境外",hsN);
  const moneyTxt=moneySum>0?("可测算金额合计约 <b style='color:#1668A8'>¥"+moneySum.toLocaleString()+"</b>（一次性与按月项混合、按月项未累计期限，仅供申报准备参考）"):"本次命中项暂无可折算金额（多为资格 / 通道 / 评审类，或该条未给出金额数值）；资格结论仍按下述条件逐条给出";
  const bar=totalN?('<div class="ovcard"><div class="ovnums">'
    +'<div class="ovn"><div class="v" style="color:#22784C">'+totalN+'</div><div class="l">✅ 现在可办（项）</div></div>'
    +'<div class="ovn"><div class="v" style="color:#B07A00">'+nearTotal+'</div><div class="l">⚠️ 差一点（项）</div></div></div>'
    +'<div class="ovacts"><button class="ovbtn pri" onclick="openChecklist()">📋 生成申报清单</button><button class="ovbtn sec" onclick="printChecklist()">🖨️ 打印 / 存PDF</button></div>'
    +'<div class="ovchips">'+chipsTxt+'</div>'
    +'<div class="ovnote">'+moneyTxt+'；金额与资格为规则估算，最终以官方最新文件及窗口审核为准，办理前可拨当地 12345 政务服务便民热线复核。</div></div>'):"";
  let out=bar;
  if(empFilled){
    out+='<div class="seclevel">✅ 你现在可以申领（就业创业）</div>'+(boxes.match.length?boxes.match.join(""):'<div class="empty">当前画像没有完全符合的补贴，展开下方“差一点”看看还缺哪些条件。</div>');
    if(boxes.near.length)out+='<div class="seclevel">⚠️ 差一点（补齐条件即可申领）</div>'+boxes.near.join("");
    if(boxes.exited.length)out+='<div class="seclevel">⛔ 已退出实施（不再受理新申请，仅备查）</div>'+boxes.exited.join("");
  }
  out+='<div class="seclevel">🎓 技能培训补贴</div>';
  out+=vtLookupHtml();
  out+=(vtMatchArr.length?vtMatchArr.join(""):'<div class="empty">勾选上方"参加目录内培训并取得证书"可匹配个人培训补贴；用上方速查器查工种金额。</div>');
  if(vtNearArr.length)out+='<div class="seclevel">⚠️ 技能培训·差一点（补齐条件即可申领）</div>'+vtNearArr.join("");
  out+=hkOut;
  out+=osOut;
  out+=entOut;
  out+=hsOut;
  document.getElementById("results").innerHTML=out;
  if(document.getElementById("vtCat"))vtLoad();
  window.LAST_RUN={total:totalN,near:nearTotal,money:moneySum,ts:new Date().toLocaleString()};if(typeof renderClientList==="function")renderClientList();
  if(!hasList())closeChecklist();
  else if(!document.getElementById("clMask").classList.contains("hide"))refreshChecklist();
}
document.getElementById("runBtn").onclick=run;
const CITY_FIELDS={};
// ★ 本仓不附带城市数据：字段池以 FIELD_TPL 统一提供，任一城市默认用同一套（9 域 × 3 主体）。
//   若某城要单独裁剪字段（例如该市没有「人才引进」域），在 CITY_FIELDS 里按城市码加一条覆盖即可。
const FIELD_TPL={"domains":["employment_startup","enterprise_support","hukou","inclusive_tax","tech_enterprise","vocational_training","housing","overseas","gba_tax"],"fields":{"person":["contract_years","has_sz_hukou","has_training_cert","identities","in_gba_youth_plan","in_key_industry","income_ok","is_family_household","is_flexible_job","is_high_end_talent","is_individual_business","is_scarce_talent","is_sz_student","no_crime_3y","no_housing_benefit","no_self_house","no_transfer_3y","pay_iit_sz","personal_ss_months","self_keygroup_or_vet","single_age_ok","sz_social_years","sz_work_days","weekly_hours","works_at_smb"],"entrepreneur":["biz_reg_months","contract_years","founder_ss_months","has_own_property","has_training_cert","hire_count","ent_ss_months","identities","is_individual_business","is_legal_rep","no_credit_violation","normal_operation","rent_addr_match","rent_months","self_keygroup_or_vet","won_city_competition"],"unit":["bought_commercial_insurance","bought_intern_insurance","contract_years","ent_scale","ent_ss_months","ent_types","free_skill_eval","has_grassroots_post","has_public_welfare_post","has_student_mid_cert","has_worker_skill_cert","hire_employdiff_count","hire_grad2y_count","hire_poverty_count","hire_trainee_count","hire_unemp6m_count","hire_veteran_within1y_count","hkmo_intern","hkmo_intern_months","hnte_certified","incubate_over_1y","incubated_success_count","is_hnte","is_labor_dispatch","is_small_low_profit","is_sme_tech","is_vat_small_scale","layoff_rate_ok","no_credit_violation","no_layoff","not_zombie","rd_expense","run_apprentice_program","staff_count","trainee_ratio_ok","ui_paid_months","ui_premium_lastyear","unemp_insurance_heads","has_training_cert","hire_count","identities","biz_reg_months","is_legal_rep","normal_operation"]}};;
document.getElementById("citySelect").onchange=function(){
  const nm=CITY_NAMES[this.value]||((this.selectedOptions&&this.selectedOptions[0])?this.selectedOptions[0].text:"本市");
  document.getElementById("cityLabel").textContent="当前匹配"+nm+"政策";
  renderMatch();
};
document.getElementById("resetBtn").onclick=()=>{renderForm();LAST={p:null,match:[],nearN:0};LASTHK={eligible:[],near:[],p:null};LASTOS={match:[],near:[],p:null};LASTENT={match:[],near:0,p:null};LASTHS={match:[],near:0,p:null};resetHkForm();resetOsForm();resetEntForm();resetHsForm();var _hb=document.getElementById("hkBox");if(_hb)_hb.open=false;var _ob=document.getElementById("osBox");if(_ob)_ob.open=false;var _eb=document.getElementById("entBox");if(_eb)_eb.open=false;var _hbb=document.getElementById("hsBox");if(_hbb)_hbb.open=false;closeChecklist();document.getElementById("clText").textContent="";document.getElementById("results").innerHTML="";document.getElementById("stat").textContent="已重置，请重新填写画像。";};
document.getElementById("copyCl").onclick=copyChecklist;
document.getElementById("dlCl").onclick=downloadChecklist;
const _dlX=document.getElementById("dlXlsx");if(_dlX)_dlX.onclick=downloadChecklistXlsx;
document.getElementById("printCl").onclick=printChecklist;
document.getElementById("closeCl").onclick=closeChecklist;
document.getElementById("clMask").onclick=e=>{if(e.target.id==="clMask")closeChecklist();};
document.addEventListener("keydown",e=>{if(e.key==="Escape"){closeChecklist();closeWb();}});
// ===== 专题场景包：加载列表 + 按场景渲染跨域政策导览 =====
var DOM_META={employment_startup:['就业创业补贴',"person"],enterprise_support:['企业用工扶持',"unit"],tech_enterprise:['科技企业扶持',"unit"],inclusive_tax:['普惠税费减免',"unit"],housing:['人才安居住房',"person"],vocational_training:['职业技能培训',"person"],hukou:['落户通道',"person"],overseas:['人才引进',"person"],gba_tax:['大湾区个税补贴',"person"]};
const RTLABEL={money:"资金/税收优惠",channel:"资格通道",review:"评审/核准"};
async function loadTopics(){
  const box=document.getElementById("topicList");
  try{const j=await(await fetch(API_BASE+"/api/v1/topics")).json();
   (j.topics||[]).forEach(t=>{
     const b=document.createElement("button");b.className="ghost";b.style.textAlign="left";b.style.padding="7px 9px";b.style.fontSize="12px";b.style.lineHeight="1.4";
     b.innerHTML='<b>'+esc(t.name)+'</b>（'+t.count+'项）<br><span style="color:#6B7280;">'+esc(t.audience||"")+'</span>';
     b.onclick=()=>openTopic(t.key);box.appendChild(b);
   });
  }catch(e){box.innerHTML='<span style="color:#c00;font-size:12px;">专题包加载失败，请确认后端已启动。</span>';}
}
async function openTopic(key){
  let d;try{d=await(await fetch(API_BASE+"/api/v1/topic/"+encodeURIComponent(key))).json();}catch(e){alert("专题包读取失败："+e.message);return;}
  const items=d.items||[];
  let h='<div class="seclevel">📚 '+esc(d.name)+'（跨域场景包 · 共 '+items.length+' 项 · 数据版本 '+d.data_version+'）</div>';
  h+='<div class="hktag" style="margin:4px 0 10px;">适用：'+esc(d.audience||"")+'　'+esc(d.desc||"")+'<br>以下为该场景串联的政策导览；填写左侧画像后点「开始匹配」，可看你/贵司具体符合哪些并做金额测算。</div>';
  h+=items.map(pol=>{
    const dl=((DOM_META[pol.domain]||[])[0]||pol.domain),rt=RTLABEL[pol.result_type]||pol.result_type;
    const valid=voff(pol.valid)?'<span class="badge b-warn">'+esc(vlabel(pol.valid))+'</span>':(pol.valid==="renamed"?'<span class="badge b-warn">已更名</span>':'');
    return '<div class="card match"><h3>'+esc(pol.name)+' <span class="badge" style="background:#EEF2F7;color:#44566B;border:1px solid #D5DEEA;">'+esc(dl)+' · '+esc(rt)+' · L'+esc(pol.depth||"?")+'</span>'+valid+'</h3>'
      +(pol.guide_url?'<div class="kv"><b>政策原文：</b><a href="'+pol.guide_url+'" target="_blank" rel="noopener" style="color:#1A5FB4;word-break:break-all;">查看原文</a></div>':'<div class="kv" style="color:#6B7280;">入口见该政策详情（填画像匹配后展示完整材料/路径/时效）</div>')
      +'</div>';
  }).join("");
  document.getElementById("results").innerHTML=h;
  document.getElementById("stat").textContent="专题场景包「"+d.name+"」共 "+items.length+" 项（"+d.data_version+"）";
  window.scrollTo({top:0,behavior:"smooth"});
}
loadTopics();
renderForm();
initBrand();
initClients();
initSubject();
document.querySelectorAll('input[name=hk_route]').forEach(o=>o.addEventListener("change",applyHkRoute));
applyHkRoute();

// ===== 商业化视图切换 =====
function showView(v){
  document.querySelectorAll('.view').forEach(function(o){o.style.display='none';});
  var t=document.getElementById('view-'+v); if(t)t.style.display='block';
  document.querySelectorAll('.topnav a').forEach(function(a){a.classList.toggle('on',a.getAttribute('data-v')===v);});
  window.scrollTo({top:0,behavior:'auto'});
}
document.querySelectorAll('.topnav a').forEach(function(a){a.addEventListener('click',function(){var v=a.getAttribute('data-v');if(v==='vt'){openVt();}else{showView(v);}});});
function goMatch(subject){
  // ★ 主体路由唯一入口（2026-10-17）：subject 必须取自前端合法集 {person,unit,entrepreneur,overseas}
  //   （与 initSubject 的 VALID / SUBJECT_WANT 同源）；'advisor' 不是申报主体而是导航，
  //   在此统一转顾问工作台 —— 否则 applySubject('advisor') 会让 SUBJECT_WANT 取到 undefined、
  //   渲染出「有按钮文案、无表单」的空页（客户可见处禁印 undefined / 禁空表单）。
  if(subject==='advisor'){goAdvisor();return;}
  setMode('self');
  if(subject)applySubject(subject);else renderMatch();
  showView('match');
}
function goAdvisor(){setMode('advisor');showView('match');if(typeof renderAdvList==="function")renderAdvList();if(typeof loadAdvisorLeads==="function")loadAdvisorLeads();}
document.getElementById('navCta').onclick=function(){goMatch('');};
document.getElementById('navAdvisor').onclick=goAdvisor;
document.getElementById('heroCta').onclick=function(){goMatch('');};
document.getElementById('leadCta').onclick=function(){document.getElementById('leadBox').scrollIntoView({behavior:'smooth'});};
document.querySelectorAll('.roleCard').forEach(function(c){c.onclick=function(){
  goMatch(c.getAttribute('data-role'));
};});
async function postLead(payload,okBox){
  try{
    var r=await fetch(API_BASE+'/api/v1/leads',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    if(!r.ok)throw new Error('http '+r.status);
    okBox.innerHTML='<b>✅ 已记录！</b>清单将发送到你留的联系方式。<br>想要顾问一对一帮你解读/测算，可加顾问微信预约演示：<span class="wechat">添加顾问微信 →（替换成你的微信号/二维码）</span>';
    okBox.style.display='block';
  }catch(e){
    okBox.textContent='提交失败（'+e.message+'），请稍后重试或直接拨打 12345。';okBox.style.display='block';
  }
}
document.getElementById('lfSubmit').onclick=function(){
  var c=document.getElementById('lfContact').value.trim();
  if(!c){alert('请留下联系方式，便于发送清单');return;}
  postLead({name:document.getElementById('lfName').value.trim(),city:document.getElementById('lfCity').value.trim(),contact:c,source:'首页清单'},document.getElementById('lfOk'));
};
// 落地页数字（取自 /meta，失败保留占位）
(async function(){
  try{
    var m=await(await fetch(API_BASE+'/api/v1/meta')).json();
    var cities=m.cities||[];
    META_CITIES=cities;if(typeof initHomeCity==='function')initHomeCity();
    document.getElementById('kCity').textContent=cities.length;
    document.getElementById('kPol').textContent=(m.total_policies||0).toLocaleString();
    document.getElementById('kDom').textContent=Object.keys(m.domains||{}).length;
    document.getElementById('cityWall').innerHTML=cities.map(function(c){return '<span>'+esc(c.name)+'</span>';}).join('');
  }catch(e){/* 离线/无后端：保留占位 */}
})();
showView('home');


document.querySelectorAll('[data-go]').forEach(function(b){b.addEventListener('click',function(){goMatch(b.getAttribute('data-go'));});});
var ab=document.getElementById('abSubmit');
if(ab)ab.onclick=function(){
  var c=document.getElementById('abContact').value.trim();
  if(!c){alert('请留下联系方式');return;}
  postLead({name:document.getElementById('abName').value.trim(),city:'',contact:c,source:'关于/合作'},document.getElementById('abOk'));
};


var META_CITIES=null;   // /meta 的城市清单（只含**真有数据**的城），由落地页 IIFE 回填
function initHomeCity(){
  var hc=document.getElementById('homeCity');if(!hc||typeof CITY_FIELDS==='undefined')return;
  // ★ 城市清单必须与落地页「已覆盖城市」墙**同源**（都取 /meta）——
  //   CITY_FIELDS 是「注册即入表」的口径（含 36 个尚无数据的城），只按它过滤会把空城
  //   列进下拉：客户选了进去是空白页（2026-10-15 批 1 注册 22 码时暴露）。
  //   静态 order 只在 /meta 尚未就绪时兜底。
  var list=(typeof META_CITIES!=='undefined'&&META_CITIES&&META_CITIES.length)
    ? META_CITIES.map(function(c){return {code:c.code,name:c.name};})
    : [];
  if(!list.length){
    // 空库（本仓默认状态）：下拉没有可选项时给明提示并把按钮变成引导，
    // 而不是留一个点了没反应的按钮。
    hc.innerHTML='<option value="">暂无城市数据</option>';
    var _go=document.getElementById('homeCityGo');
    if(_go){_go.disabled=true;_go.style.opacity='.55';_go.textContent='先接入数据 →';}
    return;
  }
  hc.innerHTML=list.map(function(c){return '<option value="'+c.code+'">'+esc(c.name)+'</option>';}).join("");
  // ★ 有数据时必须把按钮**恢复**：本函数会被调用两次（首次渲染时 /meta 还没回，
  //   走上面的空态分支把按钮禁用；/meta 到达后重跑本函数）。只设 onclick 不恢复
  //   disabled/文案，按钮就永久停在「先接入数据 →」——客户填了数据也点不进匹配页。
  var _goOk=document.getElementById('homeCityGo');
  if(_goOk){_goOk.disabled=false;_goOk.style.opacity='';_goOk.textContent='查看我能领什么 →';}
  var saved=null;try{saved=localStorage.getItem('sz_city');}catch(e){}
  if(saved&&list.some(function(c){return c.code===saved;}))hc.value=saved;
  hc.onchange=function(){try{localStorage.setItem('sz_city',hc.value);}catch(e){}};
  document.getElementById('homeCityGo').onclick=function(){
    var ms=document.getElementById('citySelect');
    if(ms){ms.value=hc.value;ms.dispatchEvent(new Event('change'));}
    try{localStorage.setItem('sz_city',hc.value);}catch(e){}
    goMatch('');
  };
}
function loadAdvisorLeads(){
  var box=document.getElementById('advLeadList');if(!box)return;
  fetch(API_BASE+'/api/v1/leads').then(function(r){return r.json();}).then(function(j){
    var ls=j.leads||[];
    box.innerHTML='<div style="font-size:12px;color:#718096;margin-bottom:6px;">共 '+ls.length+' 条线索</div>'+
      ls.slice(0,30).map(function(l){
        return '<div class="leadItem"><b>'+esc(l.name)+'</b> · '+esc(l.city||'')+'<div class="lm">'+esc(l.contact||'')+' · '+esc(l.source||'')+' · '+esc(l.created||'')+'</div></div>';
      }).join('')||'<div style="font-size:12px;color:#A0AEC0;">暂无线索</div>';
  }).catch(function(e){box.innerHTML='<div style="font-size:12px;color:#C0392B;">线索加载失败</div>';});
}
var _al=document.getElementById('advLeads'); if(_al)_al.onclick=loadAdvisorLeads;
initHomeCity();
function api(path){return fetch(API_BASE+'/api/v1'+path).then(function(r){return r.json();});}
// ★ 域名称表已上移到「专题场景包」区下方（DOM_META 单表化，2026-10-17 C 项）——此处不再重复声明。
var curDomain=null, curItems=[];
function esc(s){return (s||'').replace(/[&<>]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c];});}
function ensureDomCity(d){
 var sel=document.getElementById('domCity');
 sel.innerHTML='<option value="">全部城市</option>'+(d.cities||[]).map(function(c){return '<option value="'+c.code+'">'+c.name+'（'+c.count+'）</option>';}).join('');
 sel.onchange=function(){loadDomain(curDomain);};
}
function openDomain(k){curDomain=k;showView('domain');
 document.getElementById('domTitle').textContent=DOM_META[k][0];
 // ★ 与技能培训页同一判据：城市清单 = 该域**实际有数据的城市**（后端 /policies 现算），
 //   不再用 /meta 的全库清单 —— 那样会列出该域根本没数据的城，客户选进去只见空白。
 api('/policies?domain='+k).then(function(d){ensureDomCity(d);loadDomain(k);});
}
function loadDomain(k){
 var city=document.getElementById('domCity').value;
 var q=document.getElementById('domQ').value.trim();
 var url='/policies?domain='+k+(city?('&city='+city):'')+(q?('&q='+encodeURIComponent(q)):'');
 api(url).then(function(d){curItems=d.items;renderDom(d);});
}
function renderDom(d){
 var role=DOM_META[d.domain][1];
 document.getElementById('domMeta').textContent='数据版本 '+d.data_version+'　共 '+d.count+' 项';
 var box=document.getElementById('domList');
 if(!d.count){box.innerHTML='<div style="color:#6B7280;padding:14px;">当前筛选暂无条目，可切换城市或清除关键词。</div>';return;}
 box.innerHTML=d.items.map(function(x){
   var amt=x.amount_hint?('<span class="amt">'+esc(x.amount_hint)+'</span>'):'<span class="chip">资格 / 通道评估</span>';
   var src=x.guide_url?('<a href="'+x.guide_url+'" target="_blank">政策原文 ↗</a>'):'';
   var stChip=(x.valid&&x.valid!=="active")
      ?'<span class="chip" style="background:#FDECEC;color:#C0392B;border:1px solid #F5C6C6;">'+esc(vlabel(x.valid)||"已下线")+'</span>'
      :'<span class="chip" style="background:#EAF6EE;color:#1F7A3A;border:1px solid #B7E0C4;">现行有效</span>';
   var _dl=x.deadline;var _dlt='';var _exc='';
   if(_dl){ if(typeof _dl==='object'){_exc=execChip(_dl);
       _dlt=_dl.exec_status?(_dl.expire?('有效期至 '+_dl.expire):'')
                           :(_dl.expire||_dl.expire_text||_dl.text||_dl.cycle||'');
     }else{_dlt=String(_dl);} }
   var dl=_dlt?('<span class="win" style="color:#8A5A00;">⏰ '+esc(_dlt).slice(0,60)+'</span>'):'';
   var upd=x.updated_at?('<span class="chip" style="color:#718096;">更新 '+esc(String(x.updated_at).slice(0,10))+'</span>'):'';
   return '<div class="polrow"><div class="pn">'+esc(x.name)+' '+stChip+'</div>'
    +'<div class="meta"><span class="chip">'+x.city+'</span><span class="chip">'+(x.depth||'')+'</span>'
    +amt+'<span class="win">📅 '+esc(x.window)+'</span>'+dl+_exc+'</div>'
    +'<div class="meta">'+(x.source_doc?('<span class="chip">依据：'+esc(x.source_doc)+'</span>'):'')+upd+'</div>'
    +'<div class="acts">'+src+'<button class="mbtn" data-role="'+role+'">去匹配测算 →</button></div></div>';
 }).join('');
 box.querySelectorAll('[data-role]').forEach(function(b){b.onclick=function(){goMatch(b.getAttribute('data-role'));};});
}
// ===== 技能培训独立页（A方案） =====
var VT2_CAT=null, VT2_LOADED=false;
function openVt(){
  showView('vt');
  var sel=document.getElementById('vt2City');
  if(!VT2_LOADED){
    VT2_LOADED=true;
    // ★ 判据统一为「数据驱动」（2026-10-16）：城市清单取该域**实际有数据的城市**
    //   （后端 /policies 现算的 cities），不再拿 CITY_FIELDS 的声明域去猜 ——
    //   否则「有数据但未声明」的城（如部分城市）会被静默剔除，客户在此页选不到它
    //   （「数据在库里、客户在界面上选不到」，与 78- 的 NN 同族）。
    sel.innerHTML='<option value="">加载中…</option>';
    api('/policies?domain=vocational_training').then(function(d){
      var cs=d.cities||[];
      sel.innerHTML=cs.length
        ?cs.map(function(c){return '<option value="'+c.code+'">'+(c.name||CITY_NAMES[c.code]||c.code)+'（'+c.count+'）</option>';}).join("")
        :'<option value="">暂无可选城市</option>';
      sel.onchange=function(){VT_ORG_LOADED=false;loadVt2();};
      loadVt2();
    }).catch(function(){
      sel.innerHTML='<option value="">加载失败，请刷新</option>';
    });
    return;
  }
  loadVt2();
}
function vt2LookupHtml(){
  return '<div style="border:1px solid #D5DEEA;border-radius:10px;padding:14px;margin:8px 0;background:#F7FAFD;">'
    +'<div style="font-weight:600;font-size:14px;margin-bottom:8px;">🔍 工种补贴速查（选工种+等级，立即查能补多少）</div>'
    +'<div style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end;">'
    +'<div><label style="font-size:12px;color:#6B7280;">工种类型</label><select id="vt2Cat" style="margin-top:2px;padding:6px;">'
    +'<option value="B">职业技能等级（B类）</option><option value="D">数字技术工程师</option><option value="S">专项职业能力</option></select></div>'
    +'<div><label style="font-size:12px;color:#6B7280;">工种</label><select id="vt2Job" style="margin-top:2px;padding:6px;min-width:160px;"></select></div>'
    +'<div><label style="font-size:12px;color:#6B7280;">等级</label><select id="vt2Level" style="margin-top:2px;padding:6px;"></select></div>'
    +'</div>'
    +'<div id="vt2Result" style="margin-top:10px;font-size:14px;color:#22784C;font-weight:600;">请选择工种与等级…</div>'
    +'<div style="font-size:11px;color:#6B7280;margin-top:4px;" id="vt2Src"></div>'
    +'</div>';
}
async function loadVt2(){
  var city=document.getElementById('vt2City').value;
  document.getElementById('vt2Lookup').innerHTML=vt2LookupHtml();
  try{
    VT2_CAT=await (await fetch('/api/v1/vt_catalog?city='+city)).json();
  }catch(e){VT2_CAT={available:false};}
  vt2BuildCat();
  // 政策清单
  try{
    var d=await api('/policies?domain=vocational_training&city='+city);
    var box=document.getElementById('vt2List');
    if(!d.count){box.innerHTML='<div class="empty">该城市暂未收录培训补贴条目，可切换城市查看。</div>';}
    else{
      box.innerHTML=d.items.map(function(x){
        var amt=x.amount_hint?('<span class="amt">'+esc(x.amount_hint)+'</span>'):'<span class="chip">资格 / 通道</span>';
        var src=x.guide_url?('<a href="'+x.guide_url+'" target="_blank">政策原文 ↗</a>'):'';
        var st=(x.valid&&x.valid!=="active")?'<span class="chip" style="background:#FDECEC;color:#C0392B;">'+esc(vlabel(x.valid)||"已下线")+'</span>':'<span class="chip" style="background:#EAF6EE;color:#1F7A3A;">现行</span>';
        return '<div class="polrow"><div class="pn">'+esc(x.name)+' '+st+'</div><div class="meta"><span class="chip">'+x.city+'</span>'+amt+'</div><div class="acts">'+src+'</div></div>';
      }).join("");
    }
  }catch(e){document.getElementById('vt2List').innerHTML='<div class="empty">清单加载失败</div>';}
}
function vt2BuildCat(){
  var cat=document.getElementById('vt2Cat'),job=document.getElementById('vt2Job'),lv=document.getElementById('vt2Level');
  if(!VT2_CAT||!VT2_CAT.available){document.getElementById('vt2Result').innerText="该城市暂未收录工种目录，见下方政策清单";return;}
  function setJobs(list,withLevel){
    job.innerHTML=list.map(function(j){return '<option value="'+j.v+'">'+j.t+'</option>';}).join("");
    lv.innerHTML="";
    if(withLevel){Object.keys(VT2_CAT.level_names).forEach(function(k){lv.add(new Option(VT2_CAT.level_names[k],k));});}
    vt2Calc();
  }
  cat.onchange=function(){vt2BuildCat();};
  job.onchange=vt2Calc; lv.onchange=vt2Calc;
  if(cat.value==="B"){setJobs(VT2_CAT.B_confirmed.map(function(b){return {v:b.name,t:b.name};}),true);}
  else if(cat.value==="D"){
    var dg=VT2_CAT.digital_engineer;
    setJobs((dg.representative_jobs||[]).map(function(j){return {v:j,t:j};}),false);
    lv.innerHTML='<option value="junior">初级</option><option value="mid">中级</option><option value="senior">高级</option>';
  }else{
    var sp=VT2_CAT.special_ability;
    setJobs((sp.confirmed_items_800||[]).map(function(j){return {v:j,t:j};}),false);
  }
  vt2Calc();
}
function vt2Calc(){
  if(!VT2_CAT||!VT2_CAT.available)return;
  var cat=document.getElementById('vt2Cat').value,job=document.getElementById('vt2Job').value,lv=document.getElementById('vt2Level').value;
  var res=document.getElementById('vt2Result'),src=document.getElementById('vt2Src');
  var amt=null,note="";
  if(cat==="B"){var b=VT2_CAT.B_confirmed.find(function(x){return x.name===job;});if(b&&b.levels[lv]!=null){amt=b.levels[lv];note=job+"（"+VT2_CAT.level_names[lv]+"）";}}
  else if(cat==="D"){var la=VT2_CAT.digital_engineer.levels_amount||{};if(la[lv]!=null){amt=la[lv];note="数字技术工程师培训（"+job+"）";}}
  else{var sp=VT2_CAT.special_ability;amt=sp.amount_mostly;note="专项职业能力（"+job+"），常见 "+sp.range+" 元";}
  if(amt!=null){res.innerHTML='✅ 可申领补贴约 <b style="font-size:18px;">¥'+Number(amt).toLocaleString()+'</b> <span style="font-size:12px;color:#6B7280;font-weight:400;">'+note+'</span>';src.innerText=(VT2_CAT.source_note||"").slice(0,100);}
  else{res.innerText="该工种金额待官方目录确认";}
}
var VT_ORG_LOADED=false;
function toggleVtOrg(){
  var p=document.getElementById('vtOrgPanel');
  var open=p.style.display!=='block';
  p.style.display=open?'block':'none';
  if(open&&!VT_ORG_LOADED){VT_ORG_LOADED=true;loadVtOrg();}
}
async function loadVtOrg(){
  var city=document.getElementById('vt2City').value;
  var box=document.getElementById('vtOrgList');
  try{
    var d=await api('/policies?domain=vocational_training&city='+city);
    // 机构/企业侧：项目制、评价、学徒制等（非个人考证类）
    var orgItems=(d.items||[]).filter(function(x){
      return /项目|评价|学徒|备案|机构|企业|岗前|岗位/.test(x.name);
    });
    if(!orgItems.length)orgItems=d.items||[];
    box.innerHTML=orgItems.map(function(x){
      var amt=x.amount_hint?('<span class="amt">'+esc(x.amount_hint)+'</span>'):'';
      var src=x.guide_url?('<a href="'+x.guide_url+'" target="_blank">政策原文 ↗</a>'):'';
      return '<div class="polrow"><div class="pn">'+esc(x.name)+'</div><div class="meta">'+amt+'</div><div class="meta" style="font-size:12px;color:#4A5568;">'+esc(x.amount_hint||'按项目/人次核定')+'</div><div class="acts">'+src+'<button class="mbtn" onclick="goMatch(\'unit\')">企业视角测算 →</button></div></div>';
    }).join("")||'<div class="empty">该城市暂未收录机构侧培训项目。</div>';
  }catch(e){box.innerHTML='<div class="empty">加载失败</div>';}
}

document.querySelectorAll('[data-domain]').forEach(function(el){el.onclick=function(){openDomain(el.getAttribute('data-domain'));};});
var dq=document.getElementById('domQ');
if(dq){var t; dq.oninput=function(){clearTimeout(t);t=setTimeout(function(){loadDomain(curDomain);},350);};}
document.querySelectorAll('.soldetToggle').forEach(function(b){b.onclick=function(){var d=b.parentElement.previousElementSibling;var open=d.style.display==='block';d.style.display=open?'none':'block';b.textContent=open?'查看方案详情 ▾':'收起详情 ▴';};});

