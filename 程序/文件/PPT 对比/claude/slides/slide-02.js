const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'toc',
  index: 2,
  title: '内容概览'
};

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  // Left accent bar
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.12, h: 5.625,
    fill: { color: theme.primary }
  });

  // Section label
  slide.addText("OVERVIEW", {
    x: 0.6, y: 0.4, w: 4, h: 0.4,
    fontSize: 11, fontFace: "Arial",
    color: theme.accent, bold: true, charSpacing: 4
  });

  // Main title
  slide.addText(slideConfig.title, {
    x: 0.6, y: 0.8, w: 8, h: 0.7,
    fontSize: 36, fontFace: "Microsoft YaHei",
    color: theme.primary, bold: true
  });

  // 5 trend cards
  const trends = [
    { num: "01", title: "人工智能与通用智能", desc: "从专用AI到AGI的跨越" },
    { num: "02", title: "量子计算", desc: "突破经典计算瓶颈" },
    { num: "03", title: "生物技术与基因编辑", desc: "精准医疗与生命重塑" },
    { num: "04", title: "可持续能源", desc: "清洁能源与绿色转型" },
    { num: "05", title: "太空商业化", desc: "从近地轨道到星际探索" }
  ];

  trends.forEach((t, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const x = 0.6 + col * 4.6;
    const y = 1.7 + row * 1.2;

    // Card background
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x, y, w: 4.2, h: 1.0,
      fill: { color: "F5F7FA" },
      rectRadius: 0.08
    });

    // Number badge
    slide.addShape(pres.shapes.OVAL, {
      x: x + 0.12, y: y + 0.18, w: 0.5, h: 0.5,
      fill: { color: theme.accent }
    });
    slide.addText(t.num, {
      x: x + 0.12, y: y + 0.18, w: 0.5, h: 0.5,
      fontSize: 14, fontFace: "Arial",
      color: "FFFFFF", bold: true, align: "center", valign: "middle"
    });

    // Title
    slide.addText(t.title, {
      x: x + 0.75, y: y + 0.15, w: 3.2, h: 0.4,
      fontSize: 17, fontFace: "Microsoft YaHei",
      color: theme.primary, bold: true
    });

    // Description
    slide.addText(t.desc, {
      x: x + 0.75, y: y + 0.55, w: 3.2, h: 0.3,
      fontSize: 12, fontFace: "Microsoft YaHei",
      color: theme.secondary
    });
  });

  // Page badge
  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("2", {
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
  pres.writeFile({ fileName: "slide-02-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
