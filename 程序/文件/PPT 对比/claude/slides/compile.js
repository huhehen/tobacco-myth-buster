const pptxgen = require("pptxgenjs");
const pres = new pptxgen();
pres.layout = 'LAYOUT_16x9';
pres.author = 'Agnes AI';
pres.title = '未来十年最值得关注的五大科技趋势';

const theme = {
  primary: "000814",
  secondary: "001d3d",
  accent: "ffc300",
  light: "ffd60a",
  bg: "FFFFFF"
};

for (let i = 1; i <= 12; i++) {
  const num = String(i).padStart(2, '0');
  const slideModule = require(`./slide-${num}.js`);
  slideModule.createSlide(pres, theme);
}

pres.writeFile({ fileName: './output/presentation.pptx' })
  .then(() => console.log('PPTX generated successfully!'))
  .catch(err => console.error('Error:', err));
