const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'section-divider',
  index: 11,
  number: "05",
  title: "太空商业化"
};

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.primary };

  slide.addText(slideConfig.number, {
    x: 0.6, y: 1.2, w: 9, h: 2.5,
    fontSize: 160, fontFace: "Arial",
    color: theme.accent, opacity: 0.12, bold: true
  });

  slide.addText(slideConfig.title, {
    x: 0.6, y: 3.6, w: 8, h: 0.9,
    fontSize: 44, fontFace: "Microsoft YaHei",
    color: "FFFFFF", bold: true
  });

  slide.addText("Space Commercialization: The New Frontier", {
    x: 0.6, y: 4.5, w: 8, h: 0.5,
    fontSize: 16, fontFace: "Arial",
    color: theme.light
  });

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: 5.0, w: 2, h: 0.04,
    fill: { color: theme.accent }
  });

  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("11", {
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
  pres.writeFile({ fileName: "slide-11-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
