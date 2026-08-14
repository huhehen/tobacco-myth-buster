const pptxgen = require("pptxgenjs");

const slideConfig = {
  type: 'mixed-media',
  index: 6,
  title: '量子计算：破解经典难题'
};

function createSlide(pres, theme) {
  const slide = pres.addSlide();
  slide.background = { color: theme.bg };

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.12, h: 5.625,
    fill: { color: theme.primary }
  });

  slide.addText("02", {
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
    path: "imgs/img-quantum.png",
    x: 5.8, y: 0.6, w: 3.9, h: 4.6
  });

  // Key stat
  slide.addText("1000x", {
    x: 0.6, y: 1.5, w: 2.5, h: 0.8,
    fontSize: 56, fontFace: "Arial",
    color: theme.accent, bold: true
  });
  slide.addText("在特定问题上超越经典超级计算机的\n计算速度提升倍数（量子优越性）", {
    x: 0.6, y: 2.3, w: 4.8, h: 0.7,
    fontSize: 13, fontFace: "Microsoft YaHei",
    color: theme.secondary
  });

  // Application areas
  const apps = [
    { text: "药物研发：分子模拟与蛋白质折叠预测，缩短新药开发周期", options: { bullet: true, breakLine: true } },
    { text: "密码学：量子密钥分发（QKD）实现理论上不可破解的通信安全", options: { bullet: true, breakLine: true } },
    { text: "金融建模：蒙特卡洛模拟加速，投资组合优化与风险评估", options: { bullet: true, breakLine: true } },
    { text: "材料科学：高温超导材料设计、电池技术突破的加速器", options: { bullet: true } }
  ];
  slide.addText(apps, {
    x: 0.6, y: 3.2, w: 4.8, h: 2.2,
    fontSize: 13, fontFace: "Microsoft YaHei",
    color: theme.secondary, paraSpaceAfter: 8
  });

  // Page badge
  slide.addShape(pres.shapes.OVAL, {
    x: 9.3, y: 5.1, w: 0.4, h: 0.4,
    fill: { color: theme.accent }
  });
  slide.addText("6", {
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
  pres.writeFile({ fileName: "slide-06-preview.pptx" });
}

module.exports = { createSlide, slideConfig };
