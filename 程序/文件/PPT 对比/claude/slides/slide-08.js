const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'mixed-media',
  index: 8,
  title: '生物技术：重写生命代码'
};

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.12, h: 5.625,
    fill: { color: theme.primary }
  });

  slide.addText("03", {
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
    path: "imgs/img-biotech.png",
    x: 5.8, y: 0.6, w: 3.9, h: 4.6
  });

  // Key stat
  slide.addText("95%", {
    x: 0.6, y: 1.5, w: 2.5, h: 0.8,
    fontSize: 56, fontFace: "Arial",
    color: theme.accent, bold: true
  });
  slide.addText("CRISPR基因编辑技术的临床应用成功率\n预计将在2030年前达到", {
    x: 0.6, y: 2.3, w: 4.8, h: 0.7,
    fontSize: 13, fontFace: "Microsoft YaHei",
    color: theme.secondary
  });

  // Key areas
  const areas = [
    { text: "基因治疗：遗传病（如镰刀贫血、囊性纤维化）实现功能性治愈", options: { bullet: true, breakLine: true } },
    { text: "合成生物学：微生物工厂生产生物燃料、可降解材料与定制化学品", options: { bullet: true, breakLine: true } },
    { text: "个性化医疗：基于个体基因组信息的精准用药与癌症免疫疗法", options: { bullet: true, breakLine: true } },
    { text: "脑机接口：神经修复与认知增强，重建运动与感知能力", options: { bullet: true } }
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
  slide.addText("8", {
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
  pres.writeFile({ fileName: "slide-08-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
