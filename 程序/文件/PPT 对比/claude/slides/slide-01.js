const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'cover',
  index: 1,
  title: '未来十年最值得关注的五大科技趋势'
};

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.primary };

  // Large decorative number in background
  slide.addText("00", {
    x: 7.5, y: -0.3, w: 3, h: 2.5,
    fontSize: 180, fontFace: "Arial",
    color: theme.accent, opacity: 0.08, bold: true, align: "left"
  });

  // Accent line
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: 2.3, w: 1.2, h: 0.06,
    fill: { color: theme.accent }
  });

  // Main title
  slide.addText("未来十年最值得关注的", {
    x: 0.6, y: 1.6, w: 8, h: 0.9,
    fontSize: 42, fontFace: "Microsoft YaHei",
    color: "FFFFFF", bold: true, valign: "middle"
  });
  slide.addText("五大科技趋势", {
    x: 0.6, y: 2.45, w: 8, h: 0.9,
    fontSize: 48, fontFace: "Microsoft YaHei",
    color: theme.accent, bold: true, valign: "middle"
  });

  // Subtitle
  slide.addText("Artificial Intelligence · Quantum Computing · Biotechnology\nSustainable Energy · Space Commercialization", {
    x: 0.6, y: 3.6, w: 7, h: 1.2,
    fontSize: 14, fontFace: "Arial",
    color: theme.light, valign: "top"
  });

  // Bottom bar
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 5.2, w: 10, h: 0.425,
    fill: { color: theme.secondary }
  });
  slide.addText("2026 — 2036 科技趋势洞察", {
    x: 0.6, y: 5.25, w: 5, h: 0.35,
    fontSize: 12, fontFace: "Arial",
    color: "FFFFFF", valign: "middle"
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
  pres.writeFile({ fileName: "slide-01-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
