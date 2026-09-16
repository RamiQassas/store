import os
from pathlib import Path

target_dir = Path("apps/site/static/site/img/brands")
target_dir.mkdir(parents=True, exist_ok=True)

brands = {
    "pubg": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <defs>
    <linearGradient id="g_pubg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#f59e0b"/>
      <stop offset="100%" stop-color="#d97706"/>
    </linearGradient>
  </defs>
  <rect width="128" height="128" rx="28" fill="#111827"/>
  <circle cx="64" cy="64" r="48" fill="url(#g_pubg)" opacity="0.15"/>
  <path d="M40 38 L88 38 L88 56 L68 56 L68 90 L48 90 L48 56 L40 56 Z" fill="url(#g_pubg)"/>
  <rect x="72" y="46" width="16" height="44" rx="4" fill="#fbbf24"/>
  <text x="64" y="114" text-anchor="middle" fill="#f59e0b" font-size="14" font-weight="900" font-family="sans-serif" letter-spacing="2">PUBG</text>
</svg>""",

    "freefire": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <defs>
    <linearGradient id="g_ff" x1="0%" y1="100%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#ea580c"/>
      <stop offset="50%" stop-color="#f97316"/>
      <stop offset="100%" stop-color="#fbbf24"/>
    </linearGradient>
  </defs>
  <rect width="128" height="128" rx="28" fill="#0f172a"/>
  <path d="M64 24 C64 24, 76 42, 76 56 C76 48, 86 52, 86 64 C86 78, 74 94, 64 96 C54 94, 42 78, 42 64 C42 46, 56 34, 64 24 Z" fill="url(#g_ff)"/>
  <path d="M64 48 C64 48, 70 60, 70 68 C70 76, 64 82, 64 82 C64 82, 58 76, 58 68 C58 60, 64 48, 64 48 Z" fill="#fef08a"/>
  <text x="64" y="114" text-anchor="middle" fill="#f97316" font-size="12" font-weight="900" font-family="sans-serif" letter-spacing="1">FREE FIRE</text>
</svg>""",

    "roblox": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#1e293b"/>
  <g transform="rotate(-15 64 64)">
    <rect x="36" y="36" width="56" height="56" rx="10" fill="#ef4444"/>
    <rect x="54" y="54" width="20" height="20" rx="3" fill="#1e293b"/>
  </g>
  <text x="64" y="116" text-anchor="middle" fill="#f8fafc" font-size="13" font-weight="900" font-family="sans-serif" letter-spacing="1.5">ROBLOX</text>
</svg>""",

    "jawaker": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <defs>
    <linearGradient id="g_jw" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#dc2626"/>
      <stop offset="100%" stop-color="#991b1b"/>
    </linearGradient>
  </defs>
  <rect width="128" height="128" rx="28" fill="#09090b"/>
  <path d="M64 30 C76 16, 96 28, 96 46 C96 66, 68 84, 64 88 C60 84, 32 66, 32 46 C32 28, 52 16, 64 30 Z" fill="url(#g_jw)"/>
  <text x="64" y="114" text-anchor="middle" fill="#f87171" font-size="14" font-weight="900" font-family="sans-serif">JAWAKER</text>
</svg>""",

    "tiktok": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#000000"/>
  <g transform="translate(8, 0)">
    <path d="M58 30 L58 74 C58 84, 50 92, 40 92 C30 92, 22 84, 22 74 C22 64, 30 56, 40 56 C42 56, 44 56.5, 46 57 L46 44 C44 43.7, 42 43.5, 40 43.5 C23 43.5, 9 57.5, 9 74.5 C9 91.5, 23 105.5, 40 105.5 C57 105.5, 71 91.5, 71 74.5 L71 47 C77 51.5, 84 54, 92 54 L92 41 C82 41, 74 33, 74 23 L61 23 L61 30 Z" fill="#25f4ee" opacity="0.85" transform="translate(-3, -3)"/>
    <path d="M58 30 L58 74 C58 84, 50 92, 40 92 C30 92, 22 84, 22 74 C22 64, 30 56, 40 56 C42 56, 44 56.5, 46 57 L46 44 C44 43.7, 42 43.5, 40 43.5 C23 43.5, 9 57.5, 9 74.5 C9 91.5, 23 105.5, 40 105.5 C57 105.5, 71 91.5, 71 74.5 L71 47 C77 51.5, 84 54, 92 54 L92 41 C82 41, 74 33, 74 23 L61 23 L61 30 Z" fill="#fe2c55" opacity="0.85" transform="translate(3, 3)"/>
    <path d="M58 30 L58 74 C58 84, 50 92, 40 92 C30 92, 22 84, 22 74 C22 64, 30 56, 40 56 C42 56, 44 56.5, 46 57 L46 44 C44 43.7, 42 43.5, 40 43.5 C23 43.5, 9 57.5, 9 74.5 C9 91.5, 23 105.5, 40 105.5 C57 105.5, 71 91.5, 71 74.5 L71 47 C77 51.5, 84 54, 92 54 L92 41 C82 41, 74 33, 74 23 L61 23 L61 30 Z" fill="#ffffff"/>
  </g>
  <text x="64" y="116" text-anchor="middle" fill="#ffffff" font-size="12" font-weight="900" font-family="sans-serif">TIKTOK</text>
</svg>""",

    "netflix": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#000000"/>
  <g transform="translate(34, 22)">
    <path d="M0 0 L18 0 L18 84 L0 84 Z" fill="#b81d24"/>
    <path d="M42 0 L60 0 L60 84 L42 84 Z" fill="#b81d24"/>
    <path d="M0 0 L22 0 L60 84 L38 84 Z" fill="#e50914"/>
  </g>
  <text x="64" y="118" text-anchor="middle" fill="#e50914" font-size="12" font-weight="900" font-family="sans-serif" letter-spacing="2">NETFLIX</text>
</svg>""",

    "shahid": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <defs>
    <linearGradient id="g_sh" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#059669"/>
      <stop offset="100%" stop-color="#10b981"/>
    </linearGradient>
  </defs>
  <rect width="128" height="128" rx="28" fill="#062419"/>
  <circle cx="64" cy="54" r="34" fill="url(#g_sh)"/>
  <polygon points="56,40 78,54 56,68" fill="#ffffff"/>
  <text x="64" y="104" text-anchor="middle" fill="#34d399" font-size="14" font-weight="900" font-family="sans-serif">SHAHID VIP</text>
</svg>""",

    "telegram": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <defs>
    <linearGradient id="g_tg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#38bdf8"/>
      <stop offset="100%" stop-color="#0284c7"/>
    </linearGradient>
  </defs>
  <rect width="128" height="128" rx="28" fill="#0c1929"/>
  <circle cx="64" cy="58" r="36" fill="url(#g_tg)"/>
  <path d="M46 56 L82 42 C84 41, 86 43, 85 45 L79 73 C78 76, 75 77, 72 75 L63 68 L58 73 C57 74, 56 74, 55 73 L54 64 L74 48 C75 47, 74 46, 73 47 L49 61 L45 60 C42 59, 42 57, 46 56 Z" fill="#ffffff"/>
  <text x="64" y="114" text-anchor="middle" fill="#38bdf8" font-size="13" font-weight="800" font-family="sans-serif">TELEGRAM</text>
</svg>""",

    "googleplay": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#1e293b"/>
  <g transform="translate(32, 22)">
    <path d="M2 4 L42 42 L2 80 Z" fill="#00d3ff"/>
    <path d="M42 42 L56 28 L10 2 C6 -0.5, 2 0.5, 2 4 Z" fill="#00f076"/>
    <path d="M42 42 L66 42 L56 56 L42 42 Z" fill="#ff3a44"/>
    <path d="M42 42 L56 56 L10 82 C6 84.5, 2 83.5, 2 80 Z" fill="#ffe000"/>
  </g>
  <text x="64" y="116" text-anchor="middle" fill="#94a3b8" font-size="12" font-weight="800" font-family="sans-serif">GOOGLE PLAY</text>
</svg>""",

    "apple": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#000000"/>
  <g transform="translate(4, 0)">
    <path d="M68 20 C72 14, 78 10, 85 10 C86 17, 82 24, 76 28 C72 32, 66 34, 60 34 C59 27, 63 22, 68 20 Z" fill="#f8fafc"/>
    <path d="M84 62 C84 49, 94 43, 94 43 C88 35, 79 34, 76 34 C65 33, 59 40, 54 40 C48 40, 42 34, 34 34 C23 34, 14 42, 10 55 C4 70, 13 92, 23 104 C28 110, 33 116, 41 116 C48 116, 51 111, 59 111 C67 111, 70 116, 77 116 C85 116, 90 110, 95 103 C100 95, 103 88, 104 87 C103 86, 84 79, 84 62 Z" fill="#f8fafc"/>
  </g>
</svg>""",

    "steam": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <defs>
    <linearGradient id="g_steam" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#1b2838"/>
      <stop offset="100%" stop-color="#2a475e"/>
    </linearGradient>
  </defs>
  <rect width="128" height="128" rx="28" fill="url(#g_steam)"/>
  <circle cx="76" cy="44" r="20" fill="none" stroke="#66c0f4" stroke-width="8"/>
  <circle cx="76" cy="44" r="8" fill="#66c0f4"/>
  <circle cx="42" cy="78" r="14" fill="none" stroke="#66c0f4" stroke-width="6"/>
  <circle cx="42" cy="78" r="6" fill="#66c0f4"/>
  <line x1="62" y1="54" x2="48" y2="70" stroke="#66c0f4" stroke-width="7" stroke-linecap="round"/>
  <text x="64" y="116" text-anchor="middle" fill="#c7d5e0" font-size="13" font-weight="900" font-family="sans-serif" letter-spacing="1.5">STEAM</text>
</svg>""",

    "playstation": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#003791"/>
  <g transform="translate(20, 24)">
    <path d="M38 6 L38 68 L50 64 L50 20 L38 24 Z" fill="#ffffff"/>
    <path d="M50 20 C64 16, 76 22, 76 34 C76 46, 62 52, 50 52 Z" fill="none" stroke="#ffffff" stroke-width="8"/>
    <path d="M14 62 C28 58, 68 58, 76 68 C80 72, 74 76, 58 76 C32 76, 12 72, 14 62 Z" fill="#0070d1" opacity="0.9"/>
  </g>
  <text x="64" y="116" text-anchor="middle" fill="#ffffff" font-size="12" font-weight="900" font-family="sans-serif">PLAYSTATION</text>
</svg>""",

    "xbox": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#0e141b"/>
  <circle cx="64" cy="54" r="36" fill="#107c10"/>
  <path d="M42 34 C50 44, 58 54, 64 64 C70 54, 78 44, 86 34 C74 24, 54 24, 42 34 Z" fill="#ffffff"/>
  <path d="M34 46 C44 56, 54 68, 64 80 C56 86, 44 88, 34 84 C28 74, 28 58, 34 46 Z" fill="#ffffff"/>
  <path d="M94 46 C84 56, 74 68, 64 80 C72 86, 84 88, 94 84 C100 74, 100 58, 94 46 Z" fill="#ffffff"/>
  <text x="64" y="114" text-anchor="middle" fill="#107c10" font-size="13" font-weight="900" font-family="sans-serif" letter-spacing="2">XBOX</text>
</svg>""",

    "discord": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#5865f2"/>
  <g transform="translate(20, 24)">
    <path d="M74 14 C68 11, 62 10, 56 9 C55 11, 54 14, 53 16 C46 15, 39 15, 32 16 C31 14, 30 11, 29 9 C23 10, 17 11, 11 14 C1 29, -2 44, 1 58 C8 63, 16 67, 24 70 C26 67, 28 64, 30 60 C27 59, 24 58, 22 56 C23 55, 23 54, 24 53 C39 60, 56 60, 71 53 C72 54, 72 55, 73 56 C71 58, 68 59, 65 60 C67 64, 69 67, 71 70 C79 67, 87 63, 94 58 C97 41, 92 27, 74 14 Z M32 48 C27 48, 23 44, 23 39 C23 34, 27 30, 32 30 C37 30, 41 34, 41 39 C41 44, 37 48, 32 48 Z M63 48 C58 48, 54 44, 54 39 C54 34, 58 30, 63 30 C68 30, 72 34, 72 39 C72 44, 68 48, 63 48 Z" fill="#ffffff"/>
  </g>
  <text x="64" y="114" text-anchor="middle" fill="#ffffff" font-size="12" font-weight="800" font-family="sans-serif">DISCORD</text>
</svg>""",

    "spotify": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#121212"/>
  <circle cx="64" cy="54" r="34" fill="#1ed760"/>
  <path d="M46 44 C58 40, 74 42, 82 48 M48 54 C58 50, 70 52, 78 56 M50 64 C58 60, 68 62, 74 66" fill="none" stroke="#121212" stroke-width="5" stroke-linecap="round"/>
  <text x="64" y="114" text-anchor="middle" fill="#1ed760" font-size="13" font-weight="900" font-family="sans-serif">SPOTIFY</text>
</svg>""",

    "youtube": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#0f0f0f"/>
  <rect x="24" y="32" width="80" height="52" rx="14" fill="#ff0000"/>
  <polygon points="56,44 78,58 56,72" fill="#ffffff"/>
  <text x="64" y="114" text-anchor="middle" fill="#ff0000" font-size="12" font-weight="900" font-family="sans-serif" letter-spacing="1">YOUTUBE</text>
</svg>""",

    "snapchat": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#fffc00"/>
  <path d="M64 24 C50 24, 42 36, 42 48 C42 54, 44 60, 42 62 C40 64, 34 66, 30 68 C28 69, 28 72, 32 73 C42 75, 43 82, 38 88 C36 90, 39 92, 43 91 C50 89, 56 94, 64 94 C72 94, 78 89, 85 91 C89 92, 92 90, 90 88 C85 82, 86 75, 96 73 C100 72, 100 69, 98 68 C94 66, 88 64, 86 62 C84 60, 86 54, 86 48 C86 36, 78 24, 64 24 Z" fill="#ffffff" stroke="#000000" stroke-width="3.5"/>
</svg>""",

    "chatgpt": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#10a37f"/>
  <g transform="translate(34, 24)" stroke="#ffffff" stroke-width="4" stroke-linecap="round" fill="none">
    <circle cx="30" cy="30" r="24" opacity="0.2" fill="#ffffff"/>
    <path d="M30 6 C42 6, 50 14, 50 26 C50 34, 46 40, 38 42 L38 52 M18 42 C10 40, 6 34, 6 26 C6 14, 14 6, 26 6"/>
    <circle cx="30" cy="30" r="8" fill="#ffffff"/>
  </g>
  <text x="64" y="112" text-anchor="middle" fill="#ffffff" font-size="12" font-weight="900" font-family="sans-serif">CHATGPT / AI</text>
</svg>""",

    "canva": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <defs>
    <linearGradient id="g_canva" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#00c4cc"/>
      <stop offset="100%" stop-color="#7d2ae8"/>
    </linearGradient>
  </defs>
  <rect width="128" height="128" rx="28" fill="url(#g_canva)"/>
  <text x="64" y="76" text-anchor="middle" fill="#ffffff" font-size="42" font-weight="900" font-style="italic" font-family="serif">C</text>
  <text x="64" y="112" text-anchor="middle" fill="#ffffff" font-size="13" font-weight="900" font-family="sans-serif">CANVA PRO</text>
</svg>""",

    "vpn": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <defs>
    <linearGradient id="g_vpn" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#3b82f6"/>
      <stop offset="100%" stop-color="#1d4ed8"/>
    </linearGradient>
  </defs>
  <rect width="128" height="128" rx="28" fill="#0b1329"/>
  <path d="M64 24 L88 34 C88 56, 76 76, 64 86 C52 76, 40 56, 40 34 Z" fill="url(#g_vpn)"/>
  <circle cx="64" cy="52" r="10" fill="#ffffff"/>
  <rect x="61" y="58" width="6" height="12" rx="2" fill="#ffffff"/>
  <text x="64" y="114" text-anchor="middle" fill="#60a5fa" font-size="14" font-weight="900" font-family="sans-serif">VPN SECURE</text>
</svg>""",

    "mobilelegends": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#172554"/>
  <polygon points="64,28 78,54 104,56 82,74 90,100 64,84 38,100 46,74 24,56 50,54" fill="#fbbf24" stroke="#f59e0b" stroke-width="2"/>
  <text x="64" y="116" text-anchor="middle" fill="#93c5fd" font-size="11" font-weight="900" font-family="sans-serif">MOBILE LEGENDS</text>
</svg>""",

    "clashofclans": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#78350f"/>
  <circle cx="64" cy="54" r="34" fill="#f59e0b"/>
  <polygon points="64,28 74,48 96,54 74,60 64,80 54,60 32,54 54,48" fill="#ffffff"/>
  <text x="64" y="114" text-anchor="middle" fill="#fde68a" font-size="13" font-weight="900" font-family="sans-serif">CLASH</text>
</svg>""",

    "bigo": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#0284c7"/>
  <circle cx="64" cy="52" r="30" fill="#38bdf8"/>
  <circle cx="54" cy="48" r="5" fill="#ffffff"/>
  <circle cx="74" cy="48" r="5" fill="#ffffff"/>
  <path d="M52 64 Q64 74 76 64" fill="none" stroke="#ffffff" stroke-width="4" stroke-linecap="round"/>
  <text x="64" y="114" text-anchor="middle" fill="#ffffff" font-size="14" font-weight="900" font-family="sans-serif">BIGO LIVE</text>
</svg>""",

    "likee": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#ec4899"/>
  <path d="M64 36 C72 24, 90 32, 90 48 C90 66, 68 82, 64 86 C60 82, 38 66, 38 48 C38 32, 56 24, 64 36 Z" fill="#ffffff"/>
  <text x="64" y="114" text-anchor="middle" fill="#ffffff" font-size="14" font-weight="900" font-family="sans-serif">LIKEE</text>
</svg>""",

    "cod": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#18181b"/>
  <circle cx="64" cy="54" r="30" fill="none" stroke="#f59e0b" stroke-width="6"/>
  <line x1="64" y1="18" x2="64" y2="90" stroke="#f59e0b" stroke-width="4"/>
  <line x1="28" y1="54" x2="100" y2="54" stroke="#f59e0b" stroke-width="4"/>
  <circle cx="64" cy="54" r="8" fill="#f59e0b"/>
  <text x="64" y="114" text-anchor="middle" fill="#f59e0b" font-size="11" font-weight="900" font-family="sans-serif">CALL OF DUTY</text>
</svg>""",

    "valorant": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#0f172a"/>
  <path d="M40 36 L64 76 L64 96 L24 36 Z" fill="#ff4655"/>
  <path d="M88 36 L70 66 L60 66 L78 36 Z" fill="#ff4655"/>
  <text x="64" y="114" text-anchor="middle" fill="#ff4655" font-size="13" font-weight="900" font-family="sans-serif">VALORANT</text>
</svg>""",

    "syriatel": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#991b1b"/>
  <circle cx="64" cy="54" r="32" fill="#ef4444"/>
  <path d="M50 44 Q64 34 78 44 Q64 76 50 44 Z" fill="#ffffff"/>
  <text x="64" y="114" text-anchor="middle" fill="#ffffff" font-size="13" font-weight="900" font-family="sans-serif">SYRIATEL</text>
</svg>""",

    "yallaludo": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <defs>
    <linearGradient id="g_yl" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#047857"/>
      <stop offset="100%" stop-color="#065f46"/>
    </linearGradient>
  </defs>
  <rect width="128" height="128" rx="28" fill="url(#g_yl)"/>
  <g transform="translate(34, 22)">
    <rect x="0" y="8" width="42" height="42" rx="8" fill="#ffffff" stroke="#e2e8f0" stroke-width="2"/>
    <circle cx="21" cy="29" r="6" fill="#ef4444"/>
    <rect x="26" y="24" width="40" height="40" rx="8" fill="#fbbf24" stroke="#f59e0b" stroke-width="2"/>
    <circle cx="36" cy="34" r="4" fill="#1e293b"/>
    <circle cx="56" cy="54" r="4" fill="#1e293b"/>
    <circle cx="46" cy="44" r="4" fill="#1e293b"/>
  </g>
  <text x="64" y="114" text-anchor="middle" fill="#fde047" font-size="12" font-weight="900" font-family="sans-serif" letter-spacing="1">YALLA LUDO</text>
</svg>""",

    "razer": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#000000"/>
  <circle cx="64" cy="52" r="32" fill="#00ff00" opacity="0.12"/>
  <polygon points="64,24 88,40 88,68 64,84 40,68 40,40" fill="none" stroke="#00ff00" stroke-width="4"/>
  <polygon points="64,36 78,46 78,62 64,72 50,62 50,46" fill="#00ff00"/>
  <text x="64" y="114" text-anchor="middle" fill="#00ff00" font-size="12" font-weight="900" font-family="sans-serif" letter-spacing="1.5">RAZER GOLD</text>
</svg>""",

    "brawlstars": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#1e1b4b"/>
  <circle cx="64" cy="52" r="34" fill="#f59e0b"/>
  <polygon points="64,22 74,44 98,44 80,60 86,84 64,70 42,84 48,60 30,44 54,44" fill="#fbbf24"/>
  <circle cx="56" cy="50" r="5" fill="#1e1b4b"/>
  <circle cx="72" cy="50" r="5" fill="#1e1b4b"/>
  <text x="64" y="114" text-anchor="middle" fill="#fbbf24" font-size="11" font-weight="900" font-family="sans-serif" letter-spacing="1">BRAWL STARS</text>
</svg>""",

    "hayday": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#713f12"/>
  <circle cx="64" cy="54" r="34" fill="#eab308"/>
  <ellipse cx="64" cy="58" rx="22" ry="16" fill="#fef08a"/>
  <circle cx="56" cy="54" r="4" fill="#713f12"/>
  <circle cx="72" cy="54" r="4" fill="#713f12"/>
  <text x="64" y="114" text-anchor="middle" fill="#fef08a" font-size="14" font-weight="900" font-family="sans-serif">HAY DAY</text>
</svg>""",

    "anghami": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <defs>
    <linearGradient id="g_ang" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#9333ea"/>
      <stop offset="100%" stop-color="#db2777"/>
    </linearGradient>
  </defs>
  <rect width="128" height="128" rx="28" fill="#180c2e"/>
  <circle cx="64" cy="54" r="34" fill="url(#g_ang)"/>
  <polygon points="56,38 78,54 56,70" fill="#ffffff"/>
  <circle cx="64" cy="54" r="28" fill="none" stroke="#ffffff" stroke-width="2" opacity="0.4"/>
  <text x="64" y="114" text-anchor="middle" fill="#f472b6" font-size="13" font-weight="900" font-family="sans-serif">ANGHAMI</text>
</svg>""",

    "osn": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#881337"/>
  <circle cx="64" cy="52" r="32" fill="#be123c"/>
  <text x="56" y="62" text-anchor="middle" fill="#ffffff" font-size="24" font-weight="900" font-family="sans-serif">OSN</text>
  <text x="86" y="58" text-anchor="middle" fill="#f43f5e" font-size="28" font-weight="900" font-family="sans-serif">+</text>
  <text x="64" y="114" text-anchor="middle" fill="#fda4af" font-size="14" font-weight="900" font-family="sans-serif">OSN+</text>
</svg>""",

    "stc": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#4f008c"/>
  <path d="M40 54 Q64 34 88 54 Q64 74 40 54 Z" fill="#ff375f"/>
  <text x="64" y="114" text-anchor="middle" fill="#ffffff" font-size="15" font-weight="900" font-family="sans-serif">STC</text>
</svg>""",

    "zain": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#042f2e"/>
  <path d="M44 38 L84 38 L48 72 L84 72" fill="none" stroke="#14b8a6" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>
  <text x="64" y="114" text-anchor="middle" fill="#2dd4bf" font-size="15" font-weight="900" font-family="sans-serif">ZAIN</text>
</svg>""",

    "turkcell": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#00205b"/>
  <circle cx="64" cy="54" r="30" fill="#facc15"/>
  <path d="M50 48 Q64 36 78 48 Q64 68 50 48 Z" fill="#00205b"/>
  <text x="64" y="114" text-anchor="middle" fill="#facc15" font-size="13" font-weight="900" font-family="sans-serif">TURKCELL</text>
</svg>""",

    "vodafone": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#e60000"/>
  <circle cx="64" cy="52" r="30" fill="#ffffff"/>
  <path d="M64 38 C56 38 50 44 50 52 C50 62 60 68 64 74 C68 68 78 62 78 52 C78 44 72 38 64 38 Z" fill="#e60000"/>
  <circle cx="64" cy="52" r="6" fill="#ffffff"/>
  <text x="64" y="114" text-anchor="middle" fill="#ffffff" font-size="12" font-weight="900" font-family="sans-serif">VODAFONE</text>
</svg>""",

    "mtn": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
  <rect width="128" height="128" rx="28" fill="#ffcc00"/>
  <ellipse cx="64" cy="52" rx="42" ry="26" fill="#000000"/>
  <text x="64" y="60" text-anchor="middle" fill="#ffcc00" font-size="20" font-weight="900" font-family="sans-serif" letter-spacing="1">MTN</text>
  <text x="64" y="114" text-anchor="middle" fill="#000000" font-size="14" font-weight="900" font-family="sans-serif">MTN</text>
</svg>""",

    "generic_digital": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="100%" height="100%">
  <defs>
    <!-- Background Space Gradients -->
    <linearGradient id="rq_bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#050814"/>
      <stop offset="45%" stop-color="#0a1226"/>
      <stop offset="100%" stop-color="#03060f"/>
    </linearGradient>

    <!-- Glowing Ambient Lights -->
    <radialGradient id="cyan_ambient" cx="25%" cy="20%" r="50%">
      <stop offset="0%" stop-color="#06b6d4" stop-opacity="0.32"/>
      <stop offset="50%" stop-color="#0891b2" stop-opacity="0.12"/>
      <stop offset="100%" stop-color="#06b6d4" stop-opacity="0"/>
    </radialGradient>

    <radialGradient id="violet_ambient" cx="80%" cy="75%" r="55%">
      <stop offset="0%" stop-color="#8b5cf6" stop-opacity="0.25"/>
      <stop offset="60%" stop-color="#6366f1" stop-opacity="0.08"/>
      <stop offset="100%" stop-color="#8b5cf6" stop-opacity="0"/>
    </radialGradient>

    <radialGradient id="amber_flare" cx="85%" cy="18%" r="40%">
      <stop offset="0%" stop-color="#f59e0b" stop-opacity="0.22"/>
      <stop offset="70%" stop-color="#f59e0b" stop-opacity="0"/>
    </radialGradient>

    <!-- Card Edge Glow -->
    <linearGradient id="card_border" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.5"/>
      <stop offset="35%" stop-color="#818cf8" stop-opacity="0.25"/>
      <stop offset="70%" stop-color="#c084fc" stop-opacity="0.15"/>
      <stop offset="100%" stop-color="#38bdf8" stop-opacity="0.4"/>
    </linearGradient>

    <!-- Shield & Emblem Gradients -->
    <linearGradient id="shield_fill" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0e172f" stop-opacity="0.95"/>
      <stop offset="50%" stop-color="#0b1326" stop-opacity="0.88"/>
      <stop offset="100%" stop-color="#060b17" stop-opacity="0.98"/>
    </linearGradient>

    <linearGradient id="shield_stroke" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#22d3ee"/>
      <stop offset="50%" stop-color="#6366f1"/>
      <stop offset="100%" stop-color="#06b6d4"/>
    </linearGradient>

    <!-- Bolt Gradients (Official Brand Colors) -->
    <linearGradient id="bolt_primary" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#2dd4bf"/>
      <stop offset="50%" stop-color="#06b6d4"/>
      <stop offset="100%" stop-color="#2563eb"/>
    </linearGradient>

    <linearGradient id="bolt_highlight" x1="20%" y1="0%" x2="80%" y2="100%">
      <stop offset="0%" stop-color="#ffffff" stop-opacity="0.98"/>
      <stop offset="60%" stop-color="#e0f2fe" stop-opacity="0.92"/>
      <stop offset="100%" stop-color="#bae6fd" stop-opacity="0.85"/>
    </linearGradient>

    <!-- Typography Gradients -->
    <linearGradient id="text_gold" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#ffffff"/>
      <stop offset="50%" stop-color="#38bdf8"/>
      <stop offset="100%" stop-color="#22d3ee"/>
    </linearGradient>

    <!-- Glow Filter -->
    <filter id="glow_cyan" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="8" result="blur"/>
      <feComposite in="SourceGraphic" in2="blur" operator="over"/>
    </filter>

    <filter id="soft_drop" x="-15%" y="-15%" width="130%" height="130%">
      <feDropShadow dx="0" dy="8" stdDeviation="12" flood-color="#000000" flood-opacity="0.65"/>
    </filter>

    <!-- Pattern -->
    <pattern id="circuit_pattern" width="40" height="40" patternUnits="userSpaceOnUse">
      <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#38bdf8" stroke-width="0.75" stroke-opacity="0.06"/>
      <circle cx="40" cy="0" r="1.5" fill="#38bdf8" fill-opacity="0.12"/>
      <circle cx="0" cy="40" r="1.5" fill="#818cf8" fill-opacity="0.12"/>
    </pattern>
  </defs>

  <!-- 1. Background Rect -->
  <rect width="512" height="512" rx="72" fill="url(#rq_bg)"/>
  <rect width="512" height="512" rx="72" fill="url(#circuit_pattern)"/>

  <!-- Ambient Light Orbs -->
  <circle cx="120" cy="110" r="180" fill="url(#cyan_ambient)"/>
  <circle cx="390" cy="380" r="170" fill="url(#violet_ambient)"/>
  <circle cx="410" cy="110" r="120" fill="url(#amber_flare)"/>

  <!-- 2. Outer Border with subtle glow -->
  <rect x="12" y="12" width="488" height="488" rx="62" fill="none" stroke="url(#card_border)" stroke-width="2"/>
  <rect x="18" y="18" width="476" height="476" rx="56" fill="none" stroke="#ffffff" stroke-width="1" stroke-opacity="0.05"/>

  <!-- 3. Top Digital Tag Pill -->
  <g transform="translate(156, 36)">
    <rect width="200" height="30" rx="15" fill="#0b152d" stroke="#06b6d4" stroke-width="1" stroke-opacity="0.45"/>
    <circle cx="20" cy="15" r="4" fill="#10b981"/>
    <text x="110" y="19" text-anchor="middle" fill="#67e8f9" font-family="'Segoe UI', system-ui, sans-serif" font-size="11" font-weight="800" letter-spacing="2">RAQAMIYAT CLOUD</text>
  </g>

  <!-- 4. Central High-Tech Shield & Emblem -->
  <g filter="url(#soft_drop)" transform="translate(0, 5)">
    <!-- Outer Cyber Hexagon / Shield -->
    <polygon points="256,92 384,166 384,286 256,360 128,286 128,166" 
             fill="url(#shield_fill)" 
             stroke="url(#shield_stroke)" 
             stroke-width="2.5"/>
    
    <!-- Inner Accent Ring -->
    <polygon points="256,106 368,174 368,276 256,344 144,276 144,174" 
             fill="none" 
             stroke="#38bdf8" 
             stroke-width="1" 
             stroke-opacity="0.3" 
             stroke-dasharray="6,4"/>

    <!-- Decorative Corner Circuit Accents -->
    <line x1="128" y1="166" x2="108" y2="154" stroke="#06b6d4" stroke-width="1.5" stroke-opacity="0.6"/>
    <circle cx="108" cy="154" r="2.5" fill="#06b6d4"/>
    <line x1="384" y1="166" x2="404" y2="154" stroke="#06b6d4" stroke-width="1.5" stroke-opacity="0.6"/>
    <circle cx="404" cy="154" r="2.5" fill="#06b6d4"/>

    <line x1="128" y1="286" x2="108" y2="298" stroke="#8b5cf6" stroke-width="1.5" stroke-opacity="0.6"/>
    <circle cx="108" cy="298" r="2.5" fill="#8b5cf6"/>
    <line x1="384" y1="286" x2="404" y2="298" stroke="#8b5cf6" stroke-width="1.5" stroke-opacity="0.6"/>
    <circle cx="404" cy="298" r="2.5" fill="#8b5cf6"/>

    <!-- Official Raqamiyat Lightning Bolt Emblem (Centered & Scaled) -->
    <g transform="translate(256, 226) scale(0.52) translate(-256, -256)">
      <!-- Outer Cyan/Teal Bolt Body -->
      <path d="M285 52 128 282h108l-33 178 181-252H274L285 52Z" 
            fill="url(#bolt_primary)" 
            filter="url(#glow_cyan)"/>
      <!-- Inner Crisp White/Cyan Core Specular Highlight -->
      <path d="M260 86 158 250h108l-22 116 110-158H244l16-122Z" 
            fill="url(#bolt_highlight)"/>
    </g>
  </g>

  <!-- 5. Modern Raqamiyat Brand Typography -->
  <!-- Arabic Brand Name -->
  <text x="256" y="416" text-anchor="middle" 
        fill="url(#text_gold)" 
        font-family="'Cairo', 'Tajawal', 'Segoe UI', Arial, sans-serif" 
        font-size="34" 
        font-weight="900" 
        letter-spacing="1">رَقْمِيَّات</text>

  <!-- English Brand Name -->
  <text x="256" y="444" text-anchor="middle" 
        fill="#94a3b8" 
        font-family="'Segoe UI', -apple-system, sans-serif" 
        font-size="13" 
        font-weight="800" 
        letter-spacing="5">RAQAMIYAT</text>

  <!-- Verified Security Badge Pill -->
  <g transform="translate(136, 458)">
    <rect width="240" height="26" rx="13" fill="#091326" stroke="#38bdf8" stroke-width="1" stroke-opacity="0.35"/>
    <path d="M22 13 L25 16 L31 10" fill="none" stroke="#22d3ee" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    <text x="135" y="17" text-anchor="middle" fill="#38bdf8" font-family="'Cairo', 'Segoe UI', system-ui, sans-serif" font-size="10.5" font-weight="700" letter-spacing="1.2">منصة رقمية موثوقة • VERIFIED</text>
  </g>
</svg>"""
}

for name, svg in brands.items():
    file_path = target_dir / f"{name}.svg"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"Created {file_path}")

print("All brand SVGs successfully created!")
