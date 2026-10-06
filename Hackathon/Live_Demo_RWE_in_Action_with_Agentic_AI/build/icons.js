// Line icons (Lucide via react-icons) rendered to PNG in white / blue / navy / slate for the deck.
// Run from this folder: NODE_PATH=<dir with node_modules> node icons.js
const React = require('react'); const RDS = require('react-dom/server'); const sharp = require('sharp'); const fs = require('fs');
const lu = require('react-icons/lu');
const want = {
  // shared with Session 2
  goal: lu.LuTarget, planning: lu.LuRoute, knowledge: lu.LuBookOpen, tools: lu.LuWrench, actions: lu.LuZap, oversight: lu.LuUserCheck,
  loop: lu.LuRefreshCw, brain: lu.LuBrain, eye: lu.LuEye, play: lu.LuPlay, hospital: lu.LuHospital, calendar: lu.LuCalendarClock,
  message: lu.LuMessageSquare, phone: lu.LuSmartphone, warning: lu.LuTriangleAlert, hand: lu.LuHand, escalate: lu.LuArrowUpRight, lock: lu.LuLock,
  database: lu.LuDatabase, files: lu.LuFileText, model: lu.LuChartLine, rules: lu.LuListChecks, api: lu.LuPlug, agents: lu.LuBot, user: lu.LuUser,
  users: lu.LuUsers, shield: lu.LuShieldCheck, check: lu.LuCheck, x: lu.LuX, clock: lu.LuClock, search: lu.LuSearch, send: lu.LuSend,
  stethoscope: lu.LuStethoscope, clipboard: lu.LuClipboardList, gauge: lu.LuGauge, layers: lu.LuLayers, key: lu.LuKeyRound, log: lu.LuScrollText,
  flag: lu.LuFlag, stop: lu.LuOctagon, lightbulb: lu.LuLightbulb, question: lu.LuCircleHelp, arrowRight: lu.LuArrowRight, bell: lu.LuBell,
  pill: lu.LuPill, flask: lu.LuFlaskConical, chat: lu.LuMessagesSquare, network: lu.LuNetwork, building: lu.LuBuilding2, memory: lu.LuHistory,
  scale: lu.LuScale, sliders: lu.LuSlidersHorizontal, fence: lu.LuFence, doc: lu.LuBookMarked, thumbs: lu.LuThumbsUp, repeat: lu.LuRepeat,
  robot: lu.LuBot, star: lu.LuStar, trophy: lu.LuTrophy, alarm: lu.LuSiren, waitlist: lu.LuListOrdered, bolt: lu.LuZap, cog: lu.LuSettings, monitor: lu.LuMonitorCheck,
  // new for this session
  sparkles: lu.LuSparkles, chart: lu.LuChartColumn, table: lu.LuTable, sql: lu.LuDatabaseZap, vector: lu.LuBoxes, embed: lu.LuBinary,
  cite: lu.LuQuote, server: lu.LuServer, cpu: lu.LuCpu, puzzle: lu.LuPuzzle, link: lu.LuLink, upload: lu.LuUpload, rocket: lu.LuRocket,
  book: lu.LuBookOpenCheck, globe: lu.LuGlobe, heart: lu.LuHeartPulse, activity: lu.LuActivity, map: lu.LuMapPin, badge: lu.LuBadgeCheck,
  coins: lu.LuCoins, scan: lu.LuScanSearch, split: lu.LuSplit, wand: lu.LuWandSparkles, text: lu.LuType, trend: lu.LuTrendingUp,
  gitbranch: lu.LuGitBranch, blocks: lu.LuBlocks, workflow: lu.LuWorkflow, cloud: lu.LuCloud, folder: lu.LuFolderOpen, filecheck: lu.LuFileCheck,
  usb: lu.LuUsb, cable: lu.LuCable, pie: lu.LuChartPie, calculator: lu.LuCalculator, inbox: lu.LuInbox, hourglass: lu.LuHourglass, presentation: lu.LuPresentation,
};
(async () => {
  const missing = [];
  for (const [name, Icon] of Object.entries(want)) {
    if (!Icon) { missing.push(name); continue; }
    for (const [suffix, color] of [['w', '#FFFFFF'], ['b', '#0766D1'], ['n', '#032954'], ['g', '#7E889A']]) {
      const svg = RDS.renderToStaticMarkup(React.createElement(Icon, { color, size: 512, strokeWidth: 1.75 }));
      await sharp(Buffer.from(svg)).png().toFile(`icons/${name}_${suffix}.png`);
    }
  }
  console.log('icons done; missing:', missing.join(',') || 'none', 'count', fs.readdirSync('icons').length);
})();
