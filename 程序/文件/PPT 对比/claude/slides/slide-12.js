const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'mixed-media',
  index: 12,
  title: '太空商业化：开启新边疆'
};

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.12, h: 5.625,
    fill: { color: theme.primary }
  });

  slide.addText("05", {
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
    path: "imgs/img-space.png",
    x: 5.8, y: 0.6, w: 3.9, h: 4.6
  });

  // Key stat
  slide.addText("$1T+", {
    x: 0.6, y: 1.5, w: 2.5, h: 0.8,
    fontSize: 52, fontFace: "Arial",
    color: theme.accent, bold: true
  });
  slide.addText("2040年全球太空经济市场规模预测\n（目前约$4000亿，十年复合增速超12%）", {
    x: 0.6, y: 2.3, w: 4.8, h: 0.7,
    fontSize: 13, fontFace: "Microsoft YaHei",
    color: theme.secondary
  });

  // Key areas
  const areas = [
    { text: "可重复使用火箭：发射成本降低90%，商业航天门槛大幅降低", options: { bullet: true, breakLine: true } },
    { text: "太空制造：微重力环境下生产高纯度光纤、药物晶体与特殊合金", options: { bullet: true, breakLine: true } },
    { text: "太空旅游：亚轨道飞行商业化，从冒险进入常规消费领域", options: { bullet: true, breakLine: true } },
    { text: "月球与火星基地：各国竞争与合作并存的下一个人类前哨站", options: { bullet: true } }
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
  slide.addText("12", {
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
  pres.writeFile({ fileName: "slide-12-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
