#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Patch frontend bundle for user statistics page."""

from pathlib import Path

JS_PATH = Path(__file__).parent / "frontend_dist" / "assets" / "index-D2kbDbLZ.js"
CSS_PATH = Path(__file__).parent / "frontend_dist" / "assets" / "index-uyibihv4.css"

NEW_COMPONENT = r'''const UStatPalette=["#34d399","#60a5fa","#fbbf24","#a78bfa","#f472b6","#22d3ee","#fb923c","#94a3b8","#ef4444"];function UStatColor(e){const t=Math.abs(String(e||"").split("").reduce((n,a)=>n+a.charCodeAt(0),0));return UStatPalette[t%UStatPalette.length]}function HG({user:e,onNavigate:t,onLogout:n}){const a=tl(e),[o,s]=P.useState([]),[u,d]=P.useState([]),[p,h]=P.useState({}),[v,y]=P.useState(!0),[b,x]=P.useState({});P.useEffect(()=>{if(!a)return;(async()=>{try{y(!0);const[A,j]=await Promise.all([yb(),Zo({limit:1e4})]),S=A.filter(O=>O.is_active&&O.user_type==="regularUser");s(S);const M={};j.forEach(O=>{if(!O.personal_id)return;const C=O.item_name||"نامشخص";M[O.personal_id]||(M[O.personal_id]={}),M[O.personal_id][C]=(M[O.personal_id][C]||0)+1}),h(M);const T={};await Promise.all(S.map(async O=>{try{T[O.personal_id]=await B6(O.user_first_name,O.user_last_name)}catch{T[O.personal_id]=null}})),x(T)}catch(A){console.error("user stats load error",A)}finally{y(!1)}})()},[a]);const A=P.useMemo(()=>o.filter(j=>!u.length||u.includes(j.personal_id)).map(j=>{const S=p[j.personal_id]||{},M=Object.entries(S).map(([T,E])=>({name:T,value:E})).filter(T=>T.value>0).sort((T,E)=>E.value-T.value),C=M.reduce((T,E)=>T+E.value,0);return{user:j,chart:M,total:C}}),[o,u,p]);return f.jsxs(f.Fragment,{children:[f.jsx(wl,{activePage:"userStats",user:e,onNavigate:t,onLogout:n}),f.jsxs("main",{className:"page-main",children:[f.jsx(Al,{title:"آمار کاربران",user:e,onNavigate:t}),a?f.jsxs(f.Fragment,{children:[f.jsxs("div",{className:"page-toolbar page-card-enter user-stats-toolbar",children:[f.jsx(Cr,{label:"فیلتر کاربران",options:o.map(j=>j.personal_id),selected:u,onChange:d,getOptionLabel:j=>{const S=o.find(M=>M.personal_id===j);return S?`${S.user_first_name} ${S.user_last_name}`:String(j)}}),f.jsx("button",{type:"button",className:"page-btn page-btn-secondary",onClick:()=>d([]),children:"نمایش همه"})]}),v?f.jsx("div",{className:"dashboard-skeleton",style:{height:220,marginTop:16,borderRadius:16}}):A.length===0?f.jsx("div",{className:"dashboard-empty-state",style:{marginTop:24},children:"کاربر عادی یافت نشد"}):f.jsx("div",{className:"user-stats-grid",children:A.map(({user:j,chart:S,total:M},T)=>{const E=`${j.user_first_name} ${j.user_last_name}`,D=b[j.personal_id],I=S.some(U=>U.value>0);return f.jsxs("div",{className:"card user-stats-card dashboard-panel-enter",style:{animationDelay:`${T*0.06}s`},children:[f.jsx("div",{className:"user-stats-card-shine","aria-hidden":!0}),f.jsxs("div",{className:"user-stats-card-head",children:[D?f.jsx("img",{src:D,alt:E,className:"user-stats-avatar"}):f.jsx("div",{className:"user-stats-avatar user-stats-avatar-fallback",children:E.charAt(0)||"?"}),f.jsx("h3",{className:"user-stats-name",children:E}),f.jsxs("p",{className:"user-stats-meta",children:[M," آیتم تعمیری"]})]}),I?f.jsxs(f.Fragment,{children:[f.jsx("div",{className:"user-stats-chart",children:f.jsx(gC,{width:"100%",height:"100%",children:f.jsxs(d4,{children:[f.jsx(Zr,{data:S,dataKey:"value",nameKey:"name",innerRadius:44,outerRadius:72,paddingAngle:3,isAnimationActive:!0,animationDuration:900,children:S.map(U=>f.jsx(gd,{fill:UStatColor(U.name)},U.name))}),f.jsx(Er,{content:f.jsx(mE,{})})]})})}),f.jsx("div",{className:"user-stats-legend",children:S.map(U=>f.jsxs("span",{className:"user-stats-legend-item",children:[f.jsx("span",{className:"user-stats-legend-dot",style:{background:UStatColor(U.name)}}),U.name," (",U.value,")"]},U.name))})]}):f.jsx("div",{className:"dashboard-empty-state",style:{minHeight:110,fontSize:"0.85rem"},children:"هنوز آیتم تعمیری ثبت نشده"})]},j.personal_id)})})]}):f.jsx("div",{className:"page-panel page-card-enter",children:f.jsx("div",{className:"page-error",children:"دسترسی فقط برای مدیر و مالک"})})]})]})}'''

CSS_APPEND = """
.user-stats-toolbar{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin-top:4px}
.user-stats-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:1.1rem;margin-top:1.25rem}
.user-stats-card{position:relative;overflow:hidden;padding:1.1rem 1.15rem 1rem;border:1px solid rgba(251,146,60,.14);min-height:320px;display:flex;flex-direction:column;gap:10px}
.user-stats-card-shine{position:absolute;inset:0;background:radial-gradient(circle at 20% 0%,rgba(251,146,60,.12),transparent 55%);pointer-events:none}
.user-stats-card-head{display:flex;flex-direction:column;align-items:center;text-align:center;gap:8px;position:relative;z-index:1}
.user-stats-avatar{width:72px;height:72px;border-radius:999px;object-fit:cover;border:2px solid rgba(251,146,60,.45);box-shadow:0 10px 24px rgba(0,0,0,.45)}
.user-stats-avatar-fallback{display:flex;align-items:center;justify-content:center;background:radial-gradient(circle at 30% 20%,rgba(255,140,0,.95),rgba(255,165,0,.85));color:#111827;font-weight:800;font-size:1.4rem}
.user-stats-name{margin:0;font-size:1rem;font-weight:800;color:#f8fafc;line-height:1.35}
.user-stats-meta{margin:0;font-size:.78rem;color:#94a3b8}
.user-stats-chart{width:100%;height:170px;position:relative;z-index:1}
.user-stats-legend{display:flex;flex-wrap:wrap;gap:6px 10px;justify-content:center;position:relative;z-index:1}
.user-stats-legend-item{font-size:.72rem;color:#cbd5e1;display:inline-flex;align-items:center;gap:4px}
.user-stats-legend-dot{width:8px;height:8px;border-radius:999px;flex-shrink:0}
"""


def main() -> None:
    content = JS_PATH.read_text(encoding="utf-8")

    marker = "function $G("
    if marker not in content:
        raise SystemExit("Router marker not found")
    if "function HG(" in content:
        raise SystemExit("HG component already patched")
    content = content.replace(marker, NEW_COMPONENT + marker, 1)

    old_card = (
        'f.jsx(Gc,{title:"کاربران فعال",value:a.totalUsers,subtitle:"کاربر فعال در سیستم",'
        'icon:f.jsx(hb,{size:18}),onClick:()=>tl(e)&&t("users"),loading:x,accent:"blue",delay:.05})'
    )
    new_card = (
        'f.jsx(Gc,{title:"آمار کاربران",value:a.totalUsers,subtitle:"کاربران عادی — کلیک برای جزئیات",'
        'icon:f.jsx(hb,{size:18}),onClick:()=>tl(e)&&t("userStats"),loading:x,accent:"blue",delay:.05})'
    )
    if old_card not in content:
        raise SystemExit("Dashboard card not found")
    content = content.replace(old_card, new_card, 1)

    old_fetch = (
        "o({totalUsers:T.length,inventoryItems:D.length,pendingApproval:I,queueRepairs:U.length})"
    )
    new_fetch = (
        "o({totalUsers:T.filter(q=>q.is_active&&q.user_type===\"regularUser\").length,"
        "inventoryItems:D.length,pendingApproval:I,queueRepairs:U.length})"
    )
    if old_fetch not in content:
        raise SystemExit("Dashboard fetch not found")
    content = content.replace(old_fetch, new_fetch, 1)

    old_route = 'o==="users"&&f.jsx(BG,{user:u,onNavigate:y,onLogout:b})'
    new_route = (
        'o==="userStats"&&f.jsx(HG,{user:u,onNavigate:y,onLogout:b}),'
        + old_route
    )
    if old_route not in content:
        raise SystemExit("Router users route not found")
    content = content.replace(old_route, new_route, 1)

    JS_PATH.write_text(content, encoding="utf-8")

    css = CSS_PATH.read_text(encoding="utf-8")
    if ".user-stats-grid" not in css:
        CSS_PATH.write_text(css + CSS_APPEND, encoding="utf-8")

    print("User stats patch applied")


if __name__ == "__main__":
    main()
