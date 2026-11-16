export const THEMES=[
 {id:'light',name:'Light',description:'Fresh surfaces, ocean blue and clear contrast.',accent:'#4f7ff2',colors:['#f2f6fb','#ffffff','#123d50','#4f7ff2']},
 {id:'dark',name:'Dark',description:'Deep midnight surfaces with soft blue highlights.',accent:'#78a8ff',colors:['#101923','#182634','#0b141e','#78a8ff']},
 {id:'retro',name:'Retro',description:'Warm paper, terracotta and workshop sketches.',accent:'#a74429',colors:['#f3e8d2','#fffaf0','#493e32','#a74429']},
 {id:'classic',name:'Classic',description:'Ivory, ink blue and understated brass details.',accent:'#315773',colors:['#f4f3ef','#fffefa','#172d42','#9a7740']},
 {id:'monochrome',name:'Monochrome',description:'Quiet grayscale with crisp, focused controls.',accent:'#343434',colors:['#eeeeee','#ffffff','#222222','#696969']},
] as const;
export type AppTheme=typeof THEMES[number]['id'];
export function validTheme(value:string|null):AppTheme{return THEMES.some(t=>t.id===value)?value as AppTheme:'light'}
export function baseTheme(theme:AppTheme):'light'|'dark'{return theme==='dark'?'dark':'light'}
