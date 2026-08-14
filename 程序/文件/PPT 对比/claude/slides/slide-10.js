const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'mixed-media',
  index: 10,
  title: '可持续能源：全球绿色转型'
};

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.12, h: 5.625,
    fill: { color: theme.primary }
  });

  slide.addText("04", {
    x: 0.6, y: 0.3, w: 1, h: 0.35,
    fontSize: 11, fontFace: "Arial",
    color: theme.accent, bold: true, charSpacing: 3
  });
  slide.addText(slideConfig.title, {
    x: 0.6, y: 0.65, w: 8, h: 0.6,
    fontSize: 30, fontFace: "Microsoft YaHei",
    color: theme.primary, bold: true
  });

  // Image on right
  slide.addImage({
    path: "imgs/img-energy.png",
    x: 5.8, y: 0.6, w: 3.9, h: 4.6
  });

  // Key stat
  slide.addText("60%", {
    x: 0.6, y: 1.5, w: 2.5, h: 0.8,
    fontSize: 56, fontFace: "Arial",
    color: theme.accent, bold: true
  });
  slide.addText("可再生能源占全球新增发电装机的比例\n（2024年数据，持续攀升中）", {
    x: 0.6, y: 2.3, w: 4.8, h: 0.7,
    fontSize: 13, fontFace: "Microsoft YaHei",
    color: theme.secondary
  });

  // Key areas
  const areas = [
    { text: "新一代光伏：钙钛矿太阳能电池效率突破30%，成本进一步下降", options: { bullet: true, breakLine: true } },
    { text: "固态电池：能量密度翻倍，解决电动车续航焦虑与安全瓶颈", options: { bullet: true, breakLine: true } },
    { text: "绿氢经济：电解水制氢规模化，助力重工业脱碳与航运替代", options: { bullet: true, breakLine: true } },
    { text: "智能电网：AI调度+储能系统，实现风光发电的稳定并网与消纳", options: { bullet: true } }
  ];
  slide.addText(areas, {
    x: 0.6, y: 3.2, w: 4.8, h: 2.2,
    fontSize: 13, fontFace: "Microsoft YaHei",
    color: theme.secondary, paraSpaceAfter: 8
  });

  // Page badge
  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("10", {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fontSize: 12, fontFace: "Arial",
    color: "FFFFFF", bold: true, align: "center", valign: "middle"
  });

  return slide;
}

if (require.main === module) {
  const pres = new pptxgen();
  pres.layout = 'LAYOUT_16x9';
  const theme = {
    primary: "000814",
    secondary: "001d3d",
    accent: "ffc300",
    light: "ffd60a",
    bg: "FFFFFF"
  };
  createSlide(pres, theme);
  pres.writeFile({ fileName: "slide-10-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
