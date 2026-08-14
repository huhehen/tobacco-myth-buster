const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'mixed-media',
  index: 4,
  title: '人工智能：从专用到通用'
};

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  // Left accent bar
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.12, h: 5.625,
    fill: { color: theme.primary }
  });

  // Header
  slide.addText("01", {
    x: 0.6, y: 0.3, w: 1, h: 0.35,
    fontSize: 11, fontFace: "Arial",
    color: theme.accent, bold: true, charSpacing: 3
  });
  slide.addText(slideConfig.title, {
    x: 0.6, y: 0.65, w: 8, h: 0.6,
    fontSize: 30, fontFace: "Microsoft YaHei",
    color: theme.primary, bold: true
  });

  // Right side image
  slide.addImage({
    path: "imgs/img-ai.png",
    x: 5.8, y: 0.6, w: 3.9, h: 4.6
  });

  // Left content area
  // Key stat
  slide.addText("2030", {
    x: 0.6, y: 1.5, w: 1.8, h: 0.8,
    fontSize: 56, fontFace: "Arial",
    color: theme.accent, bold: true
  });
  slide.addText("全球AI市场规模预计达\n1.8万亿美元", {
    x: 0.6, y: 2.3, w: 4.8, h: 0.7,
    fontSize: 13, fontFace: "Microsoft YaHei",
    color: theme.secondary
  });

  // Bullet points
  const bullets = [
    { text: "AGI（通用人工智能）研究进入加速期，大模型涌现能力持续突破", options: { bullet: true, breakLine: true } },
    { text: "多模态AI深度融合：文本、图像、语音、视频统一理解与生成", options: { bullet: true, breakLine: true } },
    { text: "AI Agent成为新范式：从被动问答到自主规划与执行", options: { bullet: true, breakLine: true } },
    { text: "具身智能崛起：AI与大模型结合，赋予机器人环境感知与操作能力", options: { bullet: true } }
  ];
  slide.addText(bullets, {
    x: 0.6, y: 3.2, w: 4.8, h: 2.2,
    fontSize: 13, fontFace: "Microsoft YaHei",
    color: theme.secondary, paraSpaceAfter: 8
  });

  // Page badge
  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("4", {
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
  pres.writeFile({ fileName: "slide-04-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
