#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Patch frontend bundle for warehouse equipment type and UI updates."""

from pathlib import Path

JS_PATH = Path(__file__).parent / "frontend_dist" / "assets" / "index-D2kbDbLZ.js"


def main() -> None:
    content = JS_PATH.read_text(encoding="utf-8")
    original_len = len(content)

    # 1. Add تجهیزات to warehouse types in add-part form
    old1 = 'D=P.useMemo(()=>["نو","سالویج"],[])'
    new1 = 'D=P.useMemo(()=>["نو","سالویج","تجهیزات"],[])'
    if old1 not in content:
        raise SystemExit(f"Patch 1 not found: {old1}")
    content = content.replace(old1, new1, 1)

    # 2. Add stockCategory state and filtered list in qG
    old2 = '[h,v]=P.useState(!1),[y,b]=P.useState({partName:"",partNumber:"",entryCount:"",warehouse:"نو",entryDate:""})'
    new2 = '[h,v]=P.useState(!1),[R,F]=P.useState(null),[y,b]=P.useState({partName:"",partNumber:"",entryCount:"",warehouse:"نو",entryDate:""})'
    if old2 not in content:
        raise SystemExit(f"Patch 2 not found")
    content = content.replace(old2, new2, 1)

    old3 = '},[Q,I]),K=P.useMemo(()=>{if(!W)return[];const{stock:k,consumed:L}=W;return k<=0&&L<=0?[]:[{name:"موجودی",value:k,key:"stock"},{name:"مصرف شده",value:L,key:"used"}].filter(ee=>ee.value>0)},[W]);P.useEffect(()=>{te()},[])'
    new3 = '},[Q,I]),K=P.useMemo(()=>{if(!W)return[];const{stock:k,consumed:L}=W;return k<=0&&L<=0?[]:[{name:"موجودی",value:k,key:"stock"},{name:"مصرف شده",value:L,key:"used"}].filter(ee=>ee.value>0)},[W]),$=P.useMemo(()=>R==="equipment"?a.filter(k=>k.arsenal_name==="تجهیزات"):R==="consumable"?a.filter(k=>k.arsenal_name!=="تجهیزات"):a,[a,R]);P.useEffect(()=>{te()},[])'
    if old3 not in content:
        raise SystemExit("Patch 3 not found")
    content = content.replace(old3, new3, 1)

    # 3. Stock card opens picker
    old4 = '{id:"stock",title:"موجودی انبار",icon:ed,onClick:()=>v(!0)}'
    new4 = '{id:"stock",title:"موجودی انبار",icon:ed,onClick:()=>{v(!0),F(null)}}'
    if old4 not in content:
        raise SystemExit("Patch 4 not found")
    content = content.replace(old4, new4, 1)

    # 4. Add-part form: stack fields vertically
    old5 = 'onSubmit:ye,style:{padding:"1.5rem",display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(240px,1fr))",gap:16}'
    new5 = 'onSubmit:ye,style:{padding:"1.5rem",display:"flex",flexDirection:"column",gap:16}'
    if old5 not in content:
        raise SystemExit("Patch 5 not found")
    content = content.replace(old5, new5, 1)

    # 5. Replace stock list modal with picker + modern cards
    start_marker = 'h&&f.jsx("div",{className:"app-modal-overlay",onClick:()=>{v(!1),q(null)}'
    end_marker = '}),Q&&W&&f.jsx("div",{className:"app-modal-overlay",style:{zIndex:2050}'
    start = content.find(start_marker)
    end = content.find(end_marker, start)
    if start < 0 or end < 0:
        raise SystemExit(f"Stock modal markers not found: start={start}, end={end}")

    new_modal = '''h&&f.jsx("div",{className:"app-modal-overlay",onClick:()=>{v(!1),F(null),q(null)},children:f.jsxs("section",{className:"app-modal app-modal-lg inventory-stock-modal",onClick:k=>k.stopPropagation(),children:[f.jsxs("header",{className:"app-modal-header",children:[f.jsxs("div",{children:[f.jsx("h2",{children:R==="consumable"?"انبار مصرفی":R==="equipment"?"انبار تجهیزات":"موجودی انبار"}),f.jsx("p",{style:{margin:"4px 0 0",fontSize:"0.82rem",opacity:.85,fontWeight:500},children:R==="consumable"?"قطعات نو و سالویج":R==="equipment"?"فقط مشاهده — در تعمیرات قابل انتخاب نیست":"انتخاب نوع انبار برای مشاهده موجودی"})]}),f.jsx("button",{type:"button",className:"app-modal-close",onClick:()=>{v(!1),F(null),q(null)},children:f.jsx(Nr,{size:20})})]}),f.jsx("div",{className:"app-modal-body page-report-table-wrap",children:R?f.jsx("div",{className:"inventory-stock-shell",children:f.jsx("div",{className:"inventory-stock-list inventory-stock-list-cards",children:s?f.jsx("div",{style:{padding:"2rem",textAlign:"center",color:"#94a3b8"},children:"در حال بارگذاری..."}):$.length===0?f.jsx("div",{style:{padding:"2rem",textAlign:"center",color:"#94a3b8"},children:R==="equipment"?"قطعه تجهیزاتی ثبت نشده":"قطعه‌ای در انبار مصرفی وجود ندارد"}):$.map((k,L)=>f.jsxs("article",{role:"button",tabIndex:0,className:`inventory-stock-card ${L%2===0?"inventory-stock-card-alt":""}`,onClick:()=>q(k),onKeyDown:ee=>{(ee.key==="Enter"||ee.key===" ")&&(ee.preventDefault(),q(k))},children:[f.jsxs("div",{className:"inventory-stock-card-top",children:[f.jsx("h4",{className:"inventory-stock-card-title",title:k.fragment_name,children:k.fragment_name}),f.jsx("span",{className:`inventory-stock-card-badge inventory-stock-card-badge--${k.arsenal_name==="نو"?"new":k.arsenal_name==="سالویج"?"salvage":"equipment"}`,children:k.arsenal_name})]}),f.jsxs("div",{className:"inventory-stock-card-fields",children:[f.jsxs("div",{className:"inventory-stock-card-field",children:[f.jsx("span",{className:"inventory-stock-card-label",children:"پارت نامبر"}),f.jsx("span",{className:"inventory-stock-part-no",title:k.fragment_part_no,children:k.fragment_part_no})]}),f.jsxs("div",{className:"inventory-stock-card-field",children:[f.jsx("span",{className:"inventory-stock-card-label",children:"موجودی"}),f.jsx("span",{className:"inventory-stock-qty",children:k.fragment_qty})]})]}),R!=="equipment"?f.jsxs("div",{className:"inventory-stock-card-actions",onClick:ee=>ee.stopPropagation(),children:[f.jsxs("button",{type:"button",onClick:()=>re(k),className:"page-table-action",children:[f.jsx(V0,{size:12})," ویرایش"]}),f.jsxs("button",{type:"button",onClick:()=>X(k),className:"page-btn page-btn-danger",style:{padding:"0.35rem 0.6rem",fontSize:"0.78rem"},children:[f.jsx(Mr,{size:12})," حذف"]})]}):f.jsx("div",{className:"inventory-stock-card-viewonly",children:"فقط مشاهده"})]},`${k.fragment_part_no}-${k.arsenal_name}`))})}):f.jsx("div",{className:"inventory-stock-picker page-action-grid page-action-grid-center",children:[{id:"consumable",title:"انبار مصرفی",subtitle:"نو و سالویج",icon:ed,mode:"consumable"},{id:"equipment",title:"انبار تجهیزات",subtitle:"فقط مشاهده",icon:o2,mode:"equipment"}].map((k,L)=>f.jsx($d,{title:k.title,subtitle:k.subtitle,icon:k.icon,onClick:()=>F(k.mode),delay:.05+L*.05,className:"inventory-stock-picker-card"},k.id))})}),f.jsxs("footer",{className:"app-modal-footer",children:[R?f.jsx("button",{type:"button",onClick:()=>F(null),className:"page-btn page-btn-secondary",children:"انتخاب نوع انبار"}):null,R?f.jsx("button",{type:"button",onClick:te,className:"page-btn page-btn-primary",children:"به‌روزرسانی لیست"}):null,f.jsx("button",{type:"button",onClick:()=>{R?F(null):(v(!1),F(null),q(null))},className:"page-btn page-btn-secondary",children:R?"بستن لیست":"بازگشت"})]})]})'''

    content = content[:start] + new_modal + content[end:]

    # 6. Repairs: exclude equipment from part picker
    old6 = 'const w=await mb();ae(w),B(!0)'
    new6 = 'const w=await mb();ae(w.filter(ie=>ie.arsenal_name!=="تجهیزات")),B(!0)'
    if old6 not in content:
        raise SystemExit("Patch 6 not found")
    content = content.replace(old6, new6, 1)

    # 7. Repairs: badge color for salvage (extend existing ternary)
    old7 = 'background:w.arsenal_name==="نو"?"#dbeafe":"#fef3c7",color:w.arsenal_name==="نو"?"#1e40af":"#92400e"'
    new7 = 'background:w.arsenal_name==="نو"?"#dbeafe":w.arsenal_name==="سالویج"?"#fef3c7":"#e0e7ff",color:w.arsenal_name==="نو"?"#1e40af":w.arsenal_name==="سالویج"?"#92400e":"#3730a3"'
    if old7 in content:
        content = content.replace(old7, new7, 1)

    JS_PATH.write_text(content, encoding="utf-8")
    print(f"Patched JS: {original_len} -> {len(content)} bytes")


if __name__ == "__main__":
    main()
