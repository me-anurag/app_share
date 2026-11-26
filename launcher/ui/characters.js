/* AppShare Control Center — the two agent characters, drawn as layered vector illustrations.
   One light source (top-left): every part has a base colour, a shadow plane on the right,
   and a rim light on the upper left. No outlines. Rig groups (.c-*) are animated by CSS. */
"use strict";

const CHAR = (() => {
  let uid = 0;
  const vb = (x, y) => `style="transform-box:view-box;transform-origin:${x}px ${y}px"`;

  // ---------------------------------------------------------------- Builder: stocky maker in clay + mustard
  function builder(u) {
    const C = { base: "#c8693f", shade: "#a5512c", light: "#e08c61", deep: "#7f3b1f", mid: "#b55c35",
      dark: "#2a2622", darker: "#1d1a17", glass: "#14110f", eye: "#ffe2b0",
      hat: "#e0a83a", hatShade: "#b8842a", hatLight: "#f4c763", brim: "#c9922f", belt: "#3d3128", pouch: "#54443a", brass: "#c9a25a" };
    const torso = "M76 148 H164 Q180 148 181 164 L184 226 Q185 244 167 244 H73 Q55 244 56 226 L59 164 Q60 148 76 148 Z";
    const dome = "M52 82 C52 40 188 40 188 82 Z";
    return `
    <defs>
      <clipPath id="bt${u}"><path d="${torso}"/></clipPath>
      <clipPath id="bh${u}"><rect x="58" y="62" width="124" height="82" rx="26"/></clipPath>
      <clipPath id="bv${u}"><rect x="71" y="85" width="98" height="44" rx="18"/></clipPath>
      <clipPath id="bd${u}"><path d="${dome}"/></clipPath>
    </defs>
    <ellipse class="c-shadow" cx="120" cy="305" rx="74" ry="9" fill="#000" opacity=".38" ${vb(120, 305)}/>
    <g class="c-all" ${vb(120, 300)}>
      <!-- legs + boots -->
      <rect x="87" y="232" width="25" height="50" rx="9" fill="${C.shade}"/>
      <rect x="128" y="232" width="25" height="50" rx="9" fill="${C.deep}"/>
      <rect x="80" y="270" width="38" height="20" rx="8" fill="${C.dark}"/>
      <rect x="124" y="270" width="38" height="20" rx="8" fill="${C.dark}"/>
      <rect x="80" y="285" width="38" height="7" rx="3" fill="${C.darker}"/>
      <rect x="124" y="285" width="38" height="7" rx="3" fill="${C.darker}"/>
      <rect x="85" y="272" width="16" height="3" rx="1.5" fill="#3d3833"/>

      <!-- left arm (rests) -->
      <g class="c-armL" ${vb(62, 160)}>
        <rect x="50" y="168" width="22" height="42" rx="11" fill="${C.mid}"/>
        <circle cx="60" cy="212" r="9" fill="${C.dark}"/>
        <rect x="49" y="212" width="22" height="30" rx="10" fill="${C.base}"/>
        <rect x="47" y="236" width="26" height="8" rx="3" fill="${C.belt}"/>
        <circle cx="59" cy="250" r="14" fill="${C.dark}"/>
        <circle cx="70" cy="244" r="6" fill="${C.dark}"/>
        <circle cx="54" cy="245" r="4" fill="#3d3833"/>
        <circle cx="62" cy="160" r="17" fill="${C.base}"/>
        <circle cx="57" cy="154" r="6" fill="${C.light}" opacity=".8"/>
      </g>

      <!-- torso -->
      <g class="c-body" ${vb(120, 244)}>
        <path d="${torso}" fill="${C.base}"/>
        <g clip-path="url(#bt${u})">
          <rect x="152" y="140" width="40" height="110" fill="${C.shade}"/>
          <ellipse cx="120" cy="150" rx="44" ry="9" fill="${C.deep}" opacity=".5"/>
          <rect x="50" y="219" width="140" height="17" fill="${C.belt}"/>
        </g>
        <path d="M65 172 Q66 157 82 155 H100" fill="none" stroke="${C.light}" stroke-width="5" stroke-linecap="round"/>
        <rect x="90" y="164" width="60" height="44" rx="7" fill="${C.mid}"/>
        <rect x="98" y="171" width="44" height="30" rx="4" fill="${C.darker}"/>
        <rect x="104" y="187" width="6" height="9" rx="1" fill="${C.hat}"/>
        <rect x="114" y="181" width="6" height="15" rx="1" fill="${C.hat}"/>
        <rect x="124" y="176" width="6" height="20" rx="1" fill="${C.eye}"/>
        <rect x="134" y="184" width="3" height="12" rx="1" fill="#6b5f4f"/>
        ${[[94, 168], [146, 168], [94, 204], [146, 204]].map(([x, y]) => `<circle cx="${x}" cy="${y}" r="1.8" fill="${C.deep}"/>`).join("")}
        <rect x="110" y="218" width="20" height="18" rx="3" fill="${C.brass}"/>
        <rect x="115" y="222" width="10" height="10" rx="1.5" fill="${C.belt}"/>
        <rect x="67" y="224" width="25" height="25" rx="5" fill="${C.pouch}"/>
        <rect x="67" y="224" width="25" height="9" rx="4" fill="#64513f"/>
        <circle cx="79.5" cy="230" r="2.1" fill="${C.brass}"/>
        <circle cx="162" cy="236" r="11" fill="${C.hat}"/>
        <circle cx="160" cy="234" r="4" fill="${C.hatLight}" opacity=".6"/>
        <circle cx="162" cy="236" r="4.5" fill="${C.dark}"/>
        <rect x="167" y="243" width="11" height="4" rx="1" fill="${C.brass}"/>
      </g>

      <!-- neck -->
      <rect x="106" y="132" width="28" height="20" rx="4" fill="${C.dark}"/>
      <path d="M108 138 H132 M108 144 H132" stroke="#3d3833" stroke-width="2"/>

      <!-- right arm with the big pencil -->
      <g class="c-armR" ${vb(178, 160)}>
        <rect x="168" y="168" width="22" height="42" rx="11" fill="${C.shade}"/>
        <circle cx="180" cy="212" r="9" fill="${C.dark}"/>
        <rect x="169" y="212" width="22" height="30" rx="10" fill="${C.mid}"/>
        <rect x="167" y="236" width="26" height="8" rx="3" fill="${C.belt}"/>
        <g transform="translate(176 251) rotate(-20)">
          <rect x="-16" y="-5" width="8" height="10" rx="2.5" fill="#e08a8a"/>
          <rect x="-9" y="-5" width="9" height="10" fill="#b8b2a6"/>
          <rect x="-9" y="-5" width="9" height="3" fill="#d6d1c6"/>
          <rect x="0" y="-5" width="54" height="10" fill="#f2c14e"/>
          <rect x="0" y="0.5" width="54" height="4.5" fill="#d9a63a"/>
          <rect x="0" y="-5" width="54" height="2" fill="#f8d77e"/>
          <path d="M54 -5 L69 0 L54 5 Z" fill="#ecd3a8"/>
          <path d="M54 0.5 L69 0 L54 5 Z" fill="#d8bb8c"/>
          <path d="M63.5 -1.8 L69 0 L63.5 1.8 Z" fill="#2b2b2b"/>
        </g>
        <circle cx="180" cy="250" r="14" fill="${C.dark}"/>
        <circle cx="169" cy="244" r="6" fill="${C.dark}"/>
        <circle cx="175" cy="245" r="4" fill="#3d3833"/>
        <circle cx="178" cy="160" r="17" fill="${C.base}"/>
        <path d="M178 143 A17 17 0 0 1 195 160 A17 17 0 0 1 178 177 Z" fill="${C.shade}"/>
        <circle cx="172" cy="154" r="5" fill="${C.light}" opacity=".7"/>
      </g>

      <!-- head -->
      <g class="c-head" ${vb(120, 148)}>
        <circle cx="58" cy="106" r="13" fill="${C.dark}"/><circle cx="58" cy="106" r="5.5" fill="${C.shade}"/>
        <circle cx="182" cy="106" r="13" fill="${C.dark}"/><circle cx="182" cy="106" r="5.5" fill="${C.deep}"/>
        <rect x="58" y="62" width="124" height="82" rx="26" fill="${C.base}"/>
        <g clip-path="url(#bh${u})">
          <rect x="152" y="56" width="40" height="96" fill="${C.shade}"/>
          <rect x="50" y="133" width="140" height="14" fill="${C.shade}" opacity=".75"/>
        </g>
        <path d="M69 96 Q69 76 90 72" fill="none" stroke="${C.light}" stroke-width="5" stroke-linecap="round"/>
        <rect x="67" y="81" width="106" height="52" rx="21" fill="${C.dark}"/>
        <rect x="71" y="85" width="98" height="44" rx="18" fill="${C.glass}"/>
        <g class="c-eyes" ${vb(120, 107)}>
          <g class="e-open"><g class="c-blink" ${vb(120, 107)}>
            <rect x="92" y="95" width="16" height="25" rx="8" fill="${C.eye}"/>
            <rect x="132" y="95" width="16" height="25" rx="8" fill="${C.eye}"/>
            <rect x="95" y="99" width="4" height="7" rx="2" fill="#fff" opacity=".7"/>
            <rect x="135" y="99" width="4" height="7" rx="2" fill="#fff" opacity=".7"/>
          </g></g>
          <g class="e-happy" fill="none" stroke="${C.eye}" stroke-width="5" stroke-linecap="round">
            <path d="M91 113 Q100 99 109 113"/><path d="M131 113 Q140 99 149 113"/>
          </g>
          <g class="e-sad" fill="${C.eye}">
            <path d="M92 108 L108 100 V113 A8 8 0 0 1 92 113 Z"/><path d="M132 100 L148 108 V113 A8 8 0 0 1 132 113 Z"/>
          </g>
        </g>
        <g clip-path="url(#bv${u})">
          <path d="M71 85 H114 L92 129 H71 Z" fill="#fff" opacity=".05"/>
          <path d="M121 85 H127 L105 129 H99 Z" fill="#fff" opacity=".035"/>
        </g>
        <path d="${dome}" fill="${C.hat}"/>
        <g clip-path="url(#bd${u})"><rect x="152" y="30" width="50" height="60" fill="${C.hatShade}"/></g>
        <path d="M66 72 Q73 52 98 46" fill="none" stroke="${C.hatLight}" stroke-width="5" stroke-linecap="round"/>
        <rect x="112" y="41" width="16" height="41" rx="7" fill="#edb94b"/>
        <rect x="121" y="43" width="7" height="39" rx="3" fill="${C.hatShade}" opacity=".55"/>
        <rect x="42" y="76" width="156" height="12" rx="6" fill="${C.brim}"/>
        <rect x="47" y="76" width="96" height="3" rx="1.5" fill="${C.hatLight}" opacity=".8"/>
        <rect x="106" y="51" width="28" height="17" rx="6" fill="${C.dark}"/>
        <circle class="headlamp-lens" cx="120" cy="59.5" r="5.5" fill="#4a4238"/>
        <circle class="ant-tip" cx="171" cy="66" r="3.6" fill="#6b5f4f"/>
        <path class="headlamp-beam" d="M124 58 L300 150 L300 230 L118 64 Z" fill="#fff1d2" fill-opacity=".1"/>
      </g>
    </g>`;
  }

  // ---------------------------------------------------------------- Insights: slim hovering analyst in teal + brass
  function insights(u) {
    const C = { base: "#2f7d74", shade: "#215e57", light: "#55a99d", deep: "#163f3a",
      brass: "#c9a25a", brassShade: "#9c7a3c", brassLight: "#e6c684",
      housing: "#1b1d1c", ring: "#2c302e", iris: "#9ad3c6", irisIn: "#4d9e90", pupil: "#0d1110", dark: "#2a2622" };
    const body = "M86 158 C86 140 154 140 154 158 L150 232 C148 258 92 258 90 232 Z";
    const head = "M68 112 C68 70 172 70 172 112 C172 134 158 146 120 146 C82 146 68 134 68 112 Z";
    return `
    <defs>
      <clipPath id="ib${u}"><path d="${body}"/></clipPath>
      <clipPath id="ih${u}"><path d="${head}"/></clipPath>
      <clipPath id="il${u}"><circle cx="110" cy="108" r="26"/></clipPath>
    </defs>
    <ellipse class="c-shadow" cx="120" cy="306" rx="46" ry="7" fill="#000" opacity=".5" ${vb(120, 306)}/>
    <g class="c-all" ${vb(120, 290)}>
      <!-- hover thruster -->
      <ellipse cx="120" cy="263" rx="20" ry="6" fill="${C.brassShade}"/>
      <ellipse cx="120" cy="261" rx="15" ry="3.8" fill="${C.dark}"/>
      <path d="M108 268 L112 284 M120 269 V288 M132 268 L128 284" stroke="${C.iris}" stroke-width="2" stroke-linecap="round" opacity=".28"/>

      <!-- right arm (relaxed, away from the table) -->
      <g class="c-armR" ${vb(150, 166)}>
        <rect x="146" y="170" width="12" height="48" rx="6" fill="${C.shade}"/>
        <circle cx="152" cy="219" r="5" fill="${C.brassShade}"/>
        <rect x="147" y="219" width="11" height="18" rx="5.5" fill="${C.shade}"/>
        <circle cx="153" cy="240" r="8.5" fill="${C.base}"/>
        <circle cx="147" cy="244" r="3.8" fill="${C.base}"/>
        <circle cx="150" cy="166" r="10" fill="${C.brass}"/>
        <path d="M150 156 A10 10 0 0 1 160 166 A10 10 0 0 1 150 176 Z" fill="${C.brassShade}"/>
      </g>

      <!-- body -->
      <g class="c-body" ${vb(120, 250)}>
        <path d="${body}" fill="${C.base}"/>
        <g clip-path="url(#ib${u})">
          <rect x="130" y="130" width="40" height="140" fill="${C.shade}"/>
          <path d="M80 206 Q120 216 160 206 V270 H80 Z" fill="${C.shade}" opacity=".45"/>
        </g>
        <path d="M94 172 Q94 157 106 153" fill="none" stroke="${C.light}" stroke-width="4" stroke-linecap="round"/>
        <path d="M90 206 Q120 215 150 206" fill="none" stroke="${C.deep}" stroke-width="2"/>
        <rect x="104" y="169" width="32" height="25" rx="4" fill="${C.deep}"/>
        <rect x="109" y="184" width="5" height="6" rx="1" fill="${C.iris}"/>
        <rect x="117" y="179" width="5" height="11" rx="1" fill="${C.iris}"/>
        <rect x="125" y="174" width="5" height="16" rx="1" fill="${C.brass}"/>
        <ellipse cx="120" cy="153" rx="33" ry="7.5" fill="${C.brassShade}"/>
        <ellipse cx="120" cy="151" rx="30" ry="5.5" fill="${C.brass}"/>
        <ellipse cx="110" cy="150" rx="14" ry="2" fill="${C.brassLight}" opacity=".8"/>
      </g>

      <!-- left arm holding the tablet towards the table -->
      <g class="c-armL" ${vb(90, 166)}>
        <rect x="81" y="170" width="12" height="34" rx="6" fill="${C.base}"/>
        <circle cx="87" cy="206" r="5.5" fill="${C.brass}"/>
        <rect x="54" y="200" width="36" height="11" rx="5.5" fill="${C.base}"/>
        <g transform="rotate(-9 38 214)">
          <rect x="16" y="184" width="42" height="56" rx="5" fill="${C.dark}"/>
          <rect x="20" y="189" width="34" height="44" rx="2" fill="#1b2a2a"/>
          <g class="tablet-glow">
            <rect x="20" y="189" width="34" height="44" rx="2" fill="#dcefe9"/>
            <rect x="24" y="194" width="20" height="3" rx="1" fill="#93b3ab"/>
            <rect x="25" y="220" width="5" height="9" fill="${C.base}"/>
            <rect x="32" y="213" width="5" height="16" fill="${C.base}"/>
            <rect x="39" y="205" width="5" height="24" fill="${C.brass}"/>
            <rect x="46" y="210" width="5" height="19" fill="${C.base}"/>
          </g>
        </g>
        <circle cx="55" cy="206" r="8.5" fill="${C.base}"/>
        <circle cx="52" cy="202" r="3" fill="${C.light}" opacity=".7"/>
        <circle cx="90" cy="166" r="10" fill="${C.brass}"/>
        <circle cx="87" cy="163" r="3.5" fill="${C.brassLight}" opacity=".8"/>
      </g>

      <!-- neck -->
      <rect x="110" y="134" width="20" height="13" rx="3" fill="${C.brassShade}"/>

      <!-- head with the lens eye -->
      <g class="c-head" ${vb(120, 146)}>
        <path d="M150 78 Q156 60 162 49" fill="none" stroke="${C.brass}" stroke-width="3" stroke-linecap="round"/>
        <circle cx="150" cy="79" r="4.5" fill="${C.brassShade}"/>
        <circle class="ant-tip" cx="163" cy="46" r="6" fill="#3d6f68"/>
        <circle cx="161" cy="44" r="2" fill="#fff" opacity=".35"/>
        <path d="${head}" fill="${C.base}"/>
        <g clip-path="url(#ih${u})">
          <rect x="142" y="60" width="40" height="90" fill="${C.shade}"/>
          <rect x="60" y="134" width="120" height="14" fill="${C.shade}" opacity=".6"/>
        </g>
        <path d="M80 99 Q83 81 104 76" fill="none" stroke="${C.light}" stroke-width="5" stroke-linecap="round"/>
        <circle cx="172" cy="112" r="8.5" fill="${C.brass}"/><circle cx="172" cy="112" r="4" fill="${C.brassShade}"/>
        <circle cx="110" cy="108" r="31" fill="${C.housing}"/>
        <circle cx="110" cy="108" r="26" fill="${C.ring}"/>
        <g class="c-iris" ${vb(110, 108)}><g class="c-blink" ${vb(110, 108)}>
          <circle cx="110" cy="108" r="16.5" fill="${C.iris}"/>
          <circle cx="110" cy="108" r="10.5" fill="${C.irisIn}"/>
          <circle cx="110" cy="108" r="5.5" fill="${C.pupil}"/>
          <circle cx="104" cy="101" r="3.8" fill="#fff"/>
          <circle cx="115.5" cy="113.5" r="1.7" fill="#fff" opacity=".6"/>
        </g></g>
        <g class="e-happy" clip-path="url(#il${u})">
          <path d="M78 117 Q110 93 142 117 L142 142 L78 142 Z" fill="${C.base}"/>
          <path d="M80 116 Q110 94 140 116" fill="none" stroke="${C.shade}" stroke-width="2.5"/>
        </g>
        <g class="e-sad" clip-path="url(#il${u})">
          <path d="M78 76 L142 76 L142 97 L78 113 Z" fill="${C.base}"/>
          <path d="M78 113 L142 97" stroke="${C.shade}" stroke-width="2.5"/>
        </g>
        <path d="M86 93 A26 26 0 0 1 103 82.5" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" opacity=".22"/>
        <path class="scan-beam" ${vb(110, 108)} d="M95 101 L-110 40 L-110 210 L95 117 Z" fill="#bfe9de" fill-opacity=".09"/>
      </g>
    </g>`;
  }

  // shared face kits (screen faces): open / happy / sad
  function screenEyes(x1, x2, y, color, shape = "round") {
    const open = shape === "square"
      ? `<rect x="${x1 - 8}" y="${y - 8}" width="16" height="16" rx="4" fill="${color}"/><rect x="${x2 - 8}" y="${y - 8}" width="16" height="16" rx="4" fill="${color}"/>
         <rect x="${x1 - 5}" y="${y - 5}" width="4" height="4" rx="1" fill="#fff" opacity=".6"/><rect x="${x2 - 5}" y="${y - 5}" width="4" height="4" rx="1" fill="#fff" opacity=".6"/>`
      : `<ellipse cx="${x1}" cy="${y}" rx="6.5" ry="8.5" fill="${color}"/><ellipse cx="${x2}" cy="${y}" rx="6.5" ry="8.5" fill="${color}"/>
         <circle cx="${x1 - 2}" cy="${y - 3}" r="2" fill="#fff" opacity=".7"/><circle cx="${x2 - 2}" cy="${y - 3}" r="2" fill="#fff" opacity=".7"/>`;
    return `<g class="c-eyes" ${vb((x1 + x2) / 2, y)}>
      <g class="e-open"><g class="c-blink" ${vb((x1 + x2) / 2, y)}>${open}</g></g>
      <g class="e-happy" fill="none" stroke="${color}" stroke-width="4.5" stroke-linecap="round">
        <path d="M${x1 - 8} ${y + 4} Q${x1} ${y - 8} ${x1 + 8} ${y + 4}"/><path d="M${x2 - 8} ${y + 4} Q${x2} ${y - 8} ${x2 + 8} ${y + 4}"/></g>
      <g class="e-sad" fill="${color}">
        <path d="M${x1 - 8} ${y} L${x1 + 8} ${y - 6} V${y + 4} A8 6 0 0 1 ${x1 - 8} ${y + 4} Z"/>
        <path d="M${x2 - 8} ${y - 6} L${x2 + 8} ${y} V${y + 4} A8 6 0 0 1 ${x2 - 8} ${y + 4} Z"/></g>
    </g>`;
  }
  const legs = (c1, c2, boot, y = 246, h = 40, x1 = 92, x2 = 128, w = 20) => `
      <rect x="${x1}" y="${y}" width="${w}" height="${h}" rx="8" fill="${c1}"/><rect x="${x2}" y="${y}" width="${w}" height="${h}" rx="8" fill="${c2}"/>
      <rect x="${x1 - 6}" y="${y + h - 14}" width="${w + 12}" height="18" rx="7" fill="${boot}"/><rect x="${x2 - 6}" y="${y + h - 14}" width="${w + 12}" height="18" rx="7" fill="${boot}"/>`;

  // ---------------------------------------------------------------- Data: filing-cabinet archivist on wheels, slate blue
  function data(u) {
    const C = { base: "#4b6c93", shade: "#39557a", light: "#7194bd", deep: "#263a55", dark: "#1e242c", screen: "#10161d", eye: "#a9d8ff", brass: "#c9a25a", card: "#efe8d8" };
    return `
    <defs><clipPath id="dt${u}"><rect x="66" y="150" width="108" height="114" rx="14"/></clipPath>
      <clipPath id="dh${u}"><rect x="62" y="70" width="116" height="72" rx="18"/></clipPath></defs>
    <ellipse class="c-shadow" cx="120" cy="304" rx="62" ry="8" fill="#000" opacity=".38" ${vb(120, 304)}/>
    <g class="c-all" ${vb(120, 300)}>
      <rect x="72" y="262" width="96" height="22" rx="8" fill="${C.deep}"/>
      <circle cx="90" cy="286" r="14" fill="${C.dark}"/><circle cx="90" cy="286" r="5" fill="#4a4842"/>
      <circle cx="150" cy="286" r="14" fill="${C.dark}"/><circle cx="150" cy="286" r="5" fill="#4a4842"/>
      <g class="c-armL" ${vb(66, 166)}>
        <rect x="50" y="160" width="18" height="40" rx="9" fill="${C.base}"/><circle cx="59" cy="200" r="6" fill="${C.dark}"/>
        <rect x="49" y="200" width="18" height="30" rx="9" fill="${C.shade}"/>
        <g transform="rotate(-8 50 230)"><rect x="34" y="218" width="30" height="20" rx="2" fill="#d9cfbb"/><rect x="31" y="222" width="30" height="20" rx="2" fill="${C.card}"/>
          <rect x="35" y="227" width="20" height="2" fill="#b8432b"/><rect x="35" y="232" width="16" height="1.6" fill="#9fb3c8"/><rect x="35" y="236" width="18" height="1.6" fill="#9fb3c8"/></g>
        <circle cx="58" cy="234" r="10" fill="${C.dark}"/>
      </g>
      <g class="c-body" ${vb(120, 264)}>
        <rect x="66" y="150" width="108" height="114" rx="14" fill="${C.base}"/>
        <g clip-path="url(#dt${u})"><rect x="150" y="140" width="40" height="130" fill="${C.shade}"/><ellipse cx="120" cy="152" rx="46" ry="8" fill="${C.deep}" opacity=".5"/></g>
        <path d="M72 176 Q72 160 86 158" fill="none" stroke="${C.light}" stroke-width="4" stroke-linecap="round"/>
        <g class="c-card" ${vb(120, 190)}><rect x="104" y="168" width="32" height="22" rx="2" fill="${C.card}"/><rect x="108" y="173" width="22" height="2" fill="#b8432b"/><rect x="108" y="179" width="18" height="1.6" fill="#9fb3c8"/></g>
        <g class="c-drawer"><rect x="80" y="172" width="80" height="38" rx="4" fill="${C.shade}"/><rect x="80" y="172" width="80" height="4" rx="2" fill="${C.light}" opacity=".5"/>
          <rect x="108" y="190" width="24" height="6" rx="3" fill="${C.brass}"/><rect x="113" y="178" width="14" height="8" fill="${C.card}"/></g>
        <rect x="80" y="216" width="80" height="38" rx="4" fill="${C.shade}"/>
        <rect x="108" y="234" width="24" height="6" rx="3" fill="${C.brass}"/><rect x="113" y="222" width="14" height="8" fill="${C.card}"/>
      </g>
      <rect x="108" y="136" width="24" height="16" rx="3" fill="${C.dark}"/>
      <g class="c-armR" ${vb(174, 166)}>
        <rect x="172" y="160" width="18" height="40" rx="9" fill="${C.shade}"/><circle cx="181" cy="200" r="6" fill="${C.dark}"/>
        <rect x="173" y="200" width="18" height="30" rx="9" fill="${C.deep}"/><circle cx="182" cy="234" r="10" fill="${C.dark}"/>
      </g>
      <g class="c-head" ${vb(120, 146)}>
        <line x1="120" y1="70" x2="120" y2="52" stroke="${C.dark}" stroke-width="4"/>
        <ellipse cx="120" cy="51" rx="11" ry="4" fill="${C.brass}"/><circle class="ant-tip" cx="120" cy="45" r="4.5" fill="#4a5a6e"/>
        <rect x="54" y="94" width="12" height="28" rx="4" fill="${C.dark}"/><rect x="174" y="94" width="12" height="28" rx="4" fill="${C.dark}"/>
        <rect x="62" y="70" width="116" height="72" rx="18" fill="${C.base}"/>
        <g clip-path="url(#dh${u})"><rect x="152" y="64" width="34" height="84" fill="${C.shade}"/></g>
        <path d="M70 96 Q70 78 88 76" fill="none" stroke="${C.light}" stroke-width="4.5" stroke-linecap="round"/>
        <rect x="76" y="84" width="88" height="46" rx="10" fill="${C.screen}"/>
        ${screenEyes(104, 136, 105, C.eye, "square")}
        <rect x="96" y="120" width="48" height="2" rx="1" fill="${C.eye}" opacity=".25"/>
      </g>
    </g>`;
  }

  // ---------------------------------------------------------------- Design: plum designer with beret, brush and swatches
  function design(u) {
    const C = { base: "#8e4a68", shade: "#6d3550", light: "#b46e8f", deep: "#4f2539", dark: "#2a2226", screen: "#1a1418", eye: "#ffd8e8", beret: "#3a2a33", scarf: "#e0a83a" };
    const torso = "M90 150 Q120 140 150 150 Q166 200 160 238 Q150 256 120 256 Q90 256 80 238 Q74 200 90 150 Z";
    const sw = ["#c4471a", "#e0a83a", "#2f7d74", "#3987e5", "#8e4a68"];
    return `
    <defs><clipPath id="gt${u}"><path d="${torso}"/></clipPath><clipPath id="gh${u}"><circle cx="120" cy="104" r="40"/></clipPath></defs>
    <ellipse class="c-shadow" cx="120" cy="304" rx="50" ry="7" fill="#000" opacity=".38" ${vb(120, 304)}/>
    <g class="c-all" ${vb(120, 300)}>
      <rect x="100" y="246" width="13" height="44" rx="6.5" fill="${C.shade}"/><rect x="127" y="246" width="13" height="44" rx="6.5" fill="${C.deep}"/>
      <ellipse cx="102" cy="293" rx="16" ry="7" fill="${C.dark}"/><ellipse cx="138" cy="293" rx="16" ry="7" fill="${C.dark}"/>
      <g class="c-armL" ${vb(90, 164)}>
        <rect x="76" y="162" width="13" height="44" rx="6.5" fill="${C.base}"/>
        ${sw.map((c, i) => `<rect x="70" y="174" width="9" height="40" rx="2" fill="${c}" transform="rotate(${-40 + i * 16} 76 214)"/>`).join("")}
        <circle cx="78" cy="212" r="9" fill="${C.dark}"/>
      </g>
      <g class="c-body" ${vb(120, 256)}>
        <path d="${torso}" fill="${C.base}"/>
        <g clip-path="url(#gt${u})"><rect x="138" y="140" width="40" height="120" fill="${C.shade}"/></g>
        <path d="M86 190 Q86 166 96 156" fill="none" stroke="${C.light}" stroke-width="4" stroke-linecap="round"/>
        <circle cx="108" cy="206" r="4" fill="${sw[0]}"/><circle cx="120" cy="212" r="4" fill="${sw[2]}"/><circle cx="132" cy="206" r="4" fill="${sw[3]}"/>
        <path d="M92 152 Q120 166 148 152 L146 161 Q120 175 94 161 Z" fill="${C.scarf}"/>
        <path d="M132 160 L144 190 L134 192 L126 163 Z" fill="#c98f2a"/>
      </g>
      <rect x="112" y="134" width="16" height="13" rx="3" fill="${C.dark}"/>
      <g class="c-armR" ${vb(150, 164)}>
        <rect x="151" y="162" width="13" height="44" rx="6.5" fill="${C.shade}"/>
        <g transform="translate(160 212) rotate(-38)"><rect x="0" y="-3" width="46" height="6" rx="3" fill="#b8864a"/><rect x="0" y="-3" width="46" height="2" fill="#d6a868"/>
          <rect x="46" y="-3.6" width="8" height="7.2" fill="#b8b2a6"/><path d="M54 -4 Q63 -2 67 0 Q63 2 54 4 Z" fill="${sw[0]}"/></g>
        <circle cx="160" cy="212" r="9" fill="${C.dark}"/>
      </g>
      <g class="c-head" ${vb(120, 142)}>
        <circle cx="120" cy="104" r="40" fill="${C.base}"/>
        <g clip-path="url(#gh${u})"><rect x="138" y="60" width="30" height="90" fill="${C.shade}"/></g>
        <path d="M88 96 Q90 78 106 70" fill="none" stroke="${C.light}" stroke-width="4.5" stroke-linecap="round"/>
        <rect x="88" y="88" width="64" height="34" rx="16" fill="${C.screen}"/>
        ${screenEyes(107, 133, 105, C.eye)}
        <ellipse cx="122" cy="70" rx="45" ry="15" fill="${C.beret}" transform="rotate(-8 122 70)"/>
        <ellipse cx="114" cy="66" rx="24" ry="6" fill="#4d3843" transform="rotate(-8 114 66)" opacity=".8"/>
        <rect x="118" y="50" width="6" height="8" rx="2" fill="${C.beret}"/>
        <circle class="ant-tip" cx="121" cy="48" r="4" fill="#5a4651"/>
      </g>
    </g>`;
  }

  // ---------------------------------------------------------------- Access: olive gatekeeper with guard cap, keys and guest list
  function accessChar(u) {
    const C = { base: "#5d7442", shade: "#465a31", light: "#7f9a5c", deep: "#34431f", dark: "#262822", cap: "#2f3a2a", brim: "#1f261b", brass: "#c9a25a", face: "#e8e0cc", ink: "#262822" };
    const torso = "M64 156 Q66 146 80 146 H160 Q174 146 176 156 L168 238 Q166 250 154 250 H86 Q74 250 72 238 Z";
    return `
    <defs><clipPath id="at${u}"><path d="${torso}"/></clipPath><clipPath id="ah${u}"><rect x="72" y="76" width="96" height="68" rx="22"/></clipPath></defs>
    <ellipse class="c-shadow" cx="120" cy="304" rx="68" ry="9" fill="#000" opacity=".38" ${vb(120, 304)}/>
    <g class="c-all" ${vb(120, 300)}>
      ${legs(C.shade, C.deep, C.dark, 244, 44, 90, 128, 22)}
      <g class="c-armL" ${vb(66, 162)}>
        <rect x="50" y="160" width="20" height="42" rx="10" fill="${C.base}"/><circle cx="60" cy="202" r="6.5" fill="${C.dark}"/>
        <rect x="49" y="202" width="20" height="28" rx="9" fill="${C.shade}"/>
        <g transform="rotate(-6 50 228)"><rect x="28" y="204" width="36" height="46" rx="3" fill="#a9773f"/><rect x="32" y="210" width="28" height="36" fill="#f3eee0"/>
          <rect x="38" y="200" width="16" height="8" rx="2" fill="#8c8a7f"/>
          ${[0, 1, 2, 3].map(i => `<rect x="35" y="${215 + i * 7}" width="4" height="4" fill="none" stroke="#5d7442" stroke-width="1.2"/><rect x="42" y="${216 + i * 7}" width="${14 - i * 2}" height="1.8" fill="#8c8a7f"/>`).join("")}</g>
        <circle cx="58" cy="234" r="11" fill="${C.dark}"/>
      </g>
      <g class="c-body" ${vb(120, 250)}>
        <path d="${torso}" fill="${C.base}"/>
        <g clip-path="url(#at${u})"><rect x="148" y="140" width="40" height="120" fill="${C.shade}"/><rect x="60" y="224" width="120" height="13" fill="${C.dark}"/></g>
        <path d="M72 176 Q72 158 86 154" fill="none" stroke="${C.light}" stroke-width="4" stroke-linecap="round"/>
        <rect x="88" y="172" width="24" height="17" rx="3" fill="${C.shade}"/><rect x="88" y="172" width="24" height="5" rx="2" fill="${C.deep}"/>
        <path d="M138 166 l10 4 v7 c0 6 -4 10 -10 12 c-6 -2 -10 -6 -10 -12 v-7 z" fill="${C.brass}"/><path d="M138 170 l6 2.5 v4.5 c0 4 -3 6 -6 7.5 c-3 -1.5 -6 -3.5 -6 -7.5 v-4.5 z" fill="#e6c684"/>
        <rect x="111" y="223" width="18" height="15" rx="2" fill="${C.brass}"/>
        <circle cx="152" cy="246" r="7" fill="none" stroke="${C.brass}" stroke-width="2.5"/>
        <rect x="148" y="251" width="4" height="12" rx="1" fill="${C.brass}"/><rect x="155" y="251" width="4" height="9" rx="1" fill="#e6c684"/>
      </g>
      <rect x="108" y="132" width="24" height="18" rx="3" fill="${C.dark}"/>
      <g class="c-armR" ${vb(174, 162)}>
        <rect x="170" y="160" width="20" height="42" rx="10" fill="${C.shade}"/><circle cx="180" cy="202" r="6.5" fill="${C.dark}"/>
        <rect x="171" y="202" width="20" height="28" rx="9" fill="${C.deep}"/><circle cx="182" cy="234" r="11" fill="${C.dark}"/>
      </g>
      <g class="c-head" ${vb(120, 144)}>
        <rect x="72" y="76" width="96" height="68" rx="22" fill="${C.base}"/>
        <g clip-path="url(#ah${u})"><rect x="146" y="70" width="30" height="80" fill="${C.shade}"/></g>
        <rect x="82" y="92" width="76" height="44" rx="14" fill="${C.face}"/>
        <g class="c-eyes" ${vb(120, 112)}>
          <g class="e-open"><g class="c-blink" ${vb(120, 112)}><circle cx="104" cy="112" r="6.5" fill="${C.ink}"/><circle cx="136" cy="112" r="6.5" fill="${C.ink}"/>
            <circle cx="102" cy="110" r="2" fill="#fff"/><circle cx="134" cy="110" r="2" fill="#fff"/></g></g>
          <g class="e-happy" fill="none" stroke="${C.ink}" stroke-width="4" stroke-linecap="round"><path d="M97 115 Q104 105 111 115"/><path d="M129 115 Q136 105 143 115"/></g>
          <g class="e-sad" fill="none" stroke="${C.ink}" stroke-width="4" stroke-linecap="round"><path d="M97 110 Q104 118 111 112"/><path d="M129 112 Q136 118 143 110"/></g>
        </g>
        <path d="M112 127 q8 4 16 0" fill="none" stroke="${C.ink}" stroke-width="2.5" stroke-linecap="round"/>
        <path d="M70 86 Q72 56 120 54 Q168 56 170 86 Z" fill="${C.cap}"/>
        <rect x="70" y="78" width="100" height="9" fill="#24301f"/>
        <path d="M62 88 Q120 100 178 88 L174 95 Q120 106 66 95 Z" fill="${C.brim}"/>
        <path d="M120 60 l8 3 v6 c0 5 -3 8 -8 10 c-5 -2 -8 -5 -8 -10 v-6 z" fill="${C.brass}"/>
        <circle class="ant-tip" cx="120" cy="68" r="2.6" fill="#7a6a40"/>
      </g>
    </g>`;
  }

  // ---------------------------------------------------------------- Review: ivory proofreader with reading glasses and a red pen
  function review(u) {
    const C = { base: "#e3d9c2", shade: "#c4b89c", light: "#f6efdf", deep: "#a69a7e", dark: "#2a2724", leg: "#5a5650", eye: "#f6efdf", frame: "#8a5a2a", red: "#c8322b" };
    return `
    <defs><clipPath id="rt${u}"><rect x="74" y="152" width="92" height="100" rx="20"/></clipPath><clipPath id="rh${u}"><rect x="70" y="70" width="100" height="70" rx="24"/></clipPath></defs>
    <ellipse class="c-shadow" cx="120" cy="304" rx="58" ry="8" fill="#000" opacity=".38" ${vb(120, 304)}/>
    <g class="c-all" ${vb(120, 300)}>
      ${legs(C.leg, "#46433e", C.dark, 248, 40, 94, 126, 18)}
      <g class="c-armL" ${vb(78, 166)}>
        <rect x="62" y="162" width="16" height="44" rx="8" fill="${C.base}"/><rect x="61" y="204" width="16" height="26" rx="8" fill="${C.shade}"/>
        <g transform="rotate(-10 46 222)"><rect x="24" y="196" width="40" height="52" fill="#fbf6ea"/>
          ${[0, 1, 2, 3, 4].map(i => `<rect x="29" y="${203 + i * 8}" width="${28 - (i % 2) * 8}" height="2" fill="#bdb3a0"/>`).join("")}
          <path d="M28 222 q8 4 16 0" fill="none" stroke="${C.red}" stroke-width="1.6"/></g>
        <circle cx="69" cy="232" r="9" fill="${C.dark}"/>
      </g>
      <g class="c-body" ${vb(120, 252)}>
        <rect x="74" y="152" width="92" height="100" rx="20" fill="${C.base}"/>
        <g clip-path="url(#rt${u})"><rect x="144" y="146" width="30" height="110" fill="${C.shade}"/><ellipse cx="120" cy="154" rx="38" ry="7" fill="${C.deep}" opacity=".45"/></g>
        <path d="M100 152 L120 176 L140 152" fill="none" stroke="${C.deep}" stroke-width="3"/>
        <rect x="128" y="190" width="22" height="20" rx="3" fill="${C.shade}"/>
        <rect x="134" y="176" width="5" height="22" rx="2" fill="${C.red}"/><rect x="134" y="176" width="5" height="6" rx="2" fill="#2a2724"/>
        <path d="M82 180 Q82 162 92 158" fill="none" stroke="${C.light}" stroke-width="4" stroke-linecap="round"/>
      </g>
      <rect x="110" y="136" width="20" height="18" rx="3" fill="${C.dark}"/>
      <g class="c-armR" ${vb(162, 166)}>
        <rect x="162" y="162" width="16" height="44" rx="8" fill="${C.shade}"/><rect x="163" y="204" width="16" height="26" rx="8" fill="${C.deep}"/>
        <g transform="translate(170 234) rotate(-55)"><rect x="0" y="-2.6" width="34" height="5.2" rx="2" fill="${C.red}"/><rect x="0" y="-2.6" width="9" height="5.2" fill="#2a2724"/><path d="M34 -2.6 L40 0 L34 2.6 Z" fill="#e8d9bd"/></g>
        <circle cx="171" cy="234" r="9" fill="${C.dark}"/>
      </g>
      <g class="c-head" ${vb(120, 146)}>
        <rect x="70" y="70" width="100" height="70" rx="24" fill="${C.base}"/>
        <g clip-path="url(#rh${u})"><rect x="146" y="64" width="30" height="82" fill="${C.shade}"/></g>
        <path d="M78 96 Q78 80 94 76" fill="none" stroke="${C.light}" stroke-width="4.5" stroke-linecap="round"/>
        <rect x="80" y="86" width="80" height="40" rx="14" fill="${C.dark}"/>
        ${screenEyes(104, 136, 106, C.eye)}
        <g fill="none" stroke="${C.frame}" stroke-width="3"><circle cx="104" cy="109" r="12"/><circle cx="136" cy="109" r="12"/><path d="M116 107 q4 -3 8 0"/></g>
        <path d="M94 103 h20 M126 103 h20" stroke="${C.frame}" stroke-width="3.2"/>
        <circle class="ant-tip" cx="120" cy="66" r="4" fill="#8a7f6a"/><rect x="117" y="66" width="6" height="6" fill="${C.deep}"/>
      </g>
    </g>`;
  }

  // ---------------------------------------------------------------- Reminder: violet alarm clock with bells
  function reminder(u) {
    const C = { base: "#6a5aa8", shade: "#54478a", light: "#8a7bc8", deep: "#3b3166", dark: "#26222e", face: "#f3ecdc", brass: "#c9a25a", brassD: "#9c7a3c", ink: "#26222e" };
    const ticks = Array.from({ length: 12 }, (_, i) => { const a = i * Math.PI / 6; return `<line x1="${120 + Math.sin(a) * 42}" y1="${196 - Math.cos(a) * 42}" x2="${120 + Math.sin(a) * (i % 3 ? 46 : 48)}" y2="${196 - Math.cos(a) * (i % 3 ? 46 : 48)}" stroke="#8c8573" stroke-width="${i % 3 ? 1.5 : 3}"/>`; }).join("");
    return `
    <defs><clipPath id="mt${u}"><circle cx="120" cy="196" r="62"/></clipPath></defs>
    <ellipse class="c-shadow" cx="120" cy="304" rx="56" ry="8" fill="#000" opacity=".38" ${vb(120, 304)}/>
    <g class="c-all" ${vb(120, 300)}>
      <path d="M92 250 L82 290" stroke="${C.dark}" stroke-width="7" stroke-linecap="round"/><path d="M148 250 L158 290" stroke="${C.dark}" stroke-width="7" stroke-linecap="round"/>
      <ellipse cx="80" cy="293" rx="14" ry="6" fill="${C.dark}"/><ellipse cx="160" cy="293" rx="14" ry="6" fill="${C.dark}"/>
      <g class="c-armL" ${vb(62, 200)}>
        <path d="M62 200 Q46 206 40 222" fill="none" stroke="${C.dark}" stroke-width="6" stroke-linecap="round"/><circle cx="39" cy="226" r="8" fill="${C.base}"/>
      </g>
      <g class="c-head" ${vb(120, 150)}>
        <path d="M120 140 V124" stroke="${C.dark}" stroke-width="4"/>
        <g transform="rotate(-24 84 128)"><path d="M62 132 Q62 104 84 102 Q106 104 106 132 Z" fill="${C.brass}"/><path d="M84 102 Q106 104 106 132 H92 Q94 112 84 102 Z" fill="${C.brassD}"/><rect x="60" y="130" width="48" height="6" rx="3" fill="${C.brassD}"/></g>
        <g transform="rotate(24 156 128)"><path d="M134 132 Q134 104 156 102 Q178 104 178 132 Z" fill="${C.brass}"/><path d="M156 102 Q178 104 178 132 H164 Q166 112 156 102 Z" fill="${C.brassD}"/><rect x="132" y="130" width="48" height="6" rx="3" fill="${C.brassD}"/></g>
        <circle class="ant-tip" cx="120" cy="120" r="6" fill="#4a4258"/>
      </g>
      <g class="c-body" ${vb(120, 258)}>
        <circle cx="120" cy="196" r="62" fill="${C.base}"/>
        <g clip-path="url(#mt${u})"><circle cx="146" cy="214" r="62" fill="${C.shade}"/></g>
        <path d="M70 178 Q78 148 106 138" fill="none" stroke="${C.light}" stroke-width="5" stroke-linecap="round"/>
        <circle cx="120" cy="196" r="50" fill="${C.face}"/>
        ${ticks}
        <g class="c-hands" ${vb(120, 196)}><line x1="120" y1="196" x2="120" y2="214" stroke="${C.ink}" stroke-width="4" stroke-linecap="round"/>
          <line x1="120" y1="196" x2="142" y2="204" stroke="${C.ink}" stroke-width="3" stroke-linecap="round"/></g>
        <circle cx="120" cy="196" r="4" fill="#c8322b"/>
        ${screenEyes(104, 136, 178, C.ink)}
      </g>
      <g class="c-armR" ${vb(178, 200)}>
        <path d="M178 200 Q194 206 200 222" fill="none" stroke="${C.dark}" stroke-width="6" stroke-linecap="round"/>
        <g transform="rotate(-12 204 226)"><rect x="190" y="214" width="30" height="20" rx="2" fill="#fbf6ea"/><path d="M190 214 L205 226 L220 214" fill="none" stroke="#bdb3a0" stroke-width="1.5"/></g>
        <circle cx="200" cy="226" r="8" fill="${C.base}"/>
      </g>
    </g>`;
  }

  const DRAW = { builder, insights, data, design, access: accessChar, review, reminder };
  const HEAD_VIEW = { builder: "36 34 168 128", insights: "50 36 144 128", data: "44 36 152 120", design: "60 36 120 120",
    access: "54 44 132 116", review: "56 50 128 112", reminder: "50 90 140 164" };

  /** Full figure or a head-and-shoulders crop (for portraits and the Live view desk). */
  function svg(kind, opts = {}) {
    const u = "c" + (++uid);
    const inner = (DRAW[kind] || builder)(u);
    const view = opts.crop === "head" ? HEAD_VIEW[kind] : "0 0 240 320";
    const extra = opts.x !== undefined ? ` x="${opts.x}" y="${opts.y}" width="${opts.w}" height="${opts.h}"` : "";
    return `<svg viewBox="${view}"${extra} aria-hidden="true" class="char-svg ${kind}">${inner}</svg>`;
  }

  return { svg };
})();
