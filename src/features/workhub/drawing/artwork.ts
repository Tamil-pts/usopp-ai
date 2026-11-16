import type {Row} from '../intelligence/api';
// Original uSOPp artwork. Paths use the existing portable drawing schema.
const items=[
 ['person','Person','People','M50 10 A14 14 0 1 1 49.9 10 M20 90 V72 Q20 52 50 52 Q80 52 80 72 V90 Z'],
 ['team','Team','People','M38 12 A12 12 0 1 1 37.9 12 M68 22 A10 10 0 1 1 67.9 22 M10 85 V68 Q10 48 38 48 Q65 48 65 68 V85 Z M68 52 Q90 52 90 72 V85 H75'],
 ['check','Check','General','M12 50 L38 76 L88 22'],['warning','Warning','General','M50 8 L95 88 H5 Z M50 32 V60 M50 72 V76'],
 ['idea','Idea','General','M35 68 Q10 42 30 20 Q50 0 70 20 Q90 42 65 68 Z M35 80 H65 M40 90 H60 M50 30 V60'],
 ['target','Target','General','M50 8 A42 42 0 1 1 49.9 8 M50 25 A25 25 0 1 1 49.9 25 M50 42 A8 8 0 1 1 49.9 42'],
 ['gear','Automation','Engineering','M35 8 H65 V22 L78 30 L90 26 L98 50 L85 60 V75 L62 82 L56 95 H35 L30 80 L15 72 V55 L3 48 L12 25 L25 27 Z M50 32 A18 18 0 1 1 49.9 32'],
 ['chip','PLC chip','Engineering','M25 25 H75 V75 H25 Z M38 38 H62 V62 H38 Z M35 5 V25 M50 5 V25 M65 5 V25 M35 75 V95 M50 75 V95 M65 75 V95 M5 35 H25 M5 50 H25 M5 65 H25 M75 35 H95 M75 50 H95 M75 65 H95'],
 ['server','Server','Technology','M15 10 H85 V35 H15 Z M15 40 H85 V65 H15 Z M15 70 H85 V95 H15 Z M25 22 H30 M25 52 H30 M25 82 H30'],
 ['cloud','Cloud','Technology','M25 75 Q0 75 8 50 Q12 35 30 38 Q30 6 58 16 Q78 18 78 40 Q100 38 95 62 Q92 75 75 75 Z'],
 ['database','Database','Technology','M15 25 C15 5 85 5 85 25 C85 45 15 45 15 25 V75 C15 95 85 95 85 75 V25 M15 50 C15 70 85 70 85 50'],
 ['document','Document','General','M20 5 H60 L85 30 V95 H20 Z M60 5 V30 H85 M32 45 H72 M32 60 H72 M32 75 H62'],
 ['flag','Milestone','Planning','M20 95 V10 M20 10 H85 L68 30 L85 50 H20'],
 ['calendar','Calendar','Planning','M10 20 H90 V90 H10 Z M10 40 H90 M30 5 V30 M70 5 V30 M28 55 H38 M48 55 H58 M68 55 H78 M28 72 H38 M48 72 H58'],
 ['chart','Bar chart','Planning','M10 5 V90 H95 M25 70 V50 H38 V70 Z M48 70 V30 H61 V70 Z M71 70 V10 H84 V70 Z'],
 ['factory','Factory','Clip art','M5 90 V45 L35 25 V45 L65 25 V45 H95 V90 Z M72 45 V5 H86 V45 M18 62 H28 V76 H18 Z M44 62 H54 V76 H44 Z M70 62 H80 V76 H70 Z'],
 ['mountain','Mountain goal','Clip art','M3 90 L35 32 L48 54 L65 15 L97 90 Z M52 42 L65 15 L78 43 M65 15 V3 H88 L78 10 H65'],
 ['rocket','Rocket','Clip art','M35 65 Q24 25 60 5 Q90 30 65 65 Z M35 50 L12 60 V85 L35 70 M65 50 L88 60 V85 L65 70 M43 76 L50 97 L57 76 M50 28 A8 8 0 1 1 49.9 28'],
 ['trophy','Trophy','Clip art','M30 10 H70 V40 Q70 65 50 65 Q30 65 30 40 Z M30 20 H10 V35 Q10 55 32 55 M70 20 H90 V35 Q90 55 68 55 M50 65 V85 M30 90 H70'],
 ['handshake','Connection','Clip art','M5 35 L25 20 L45 30 L60 20 L95 40 L78 75 L65 82 L30 65 Z M45 30 L30 45 L42 53 L57 40 L78 60 M25 20 L12 55 M95 40 L82 70']
];
export const artwork:Row={id:'usopp-artwork',name:'Icons & Clip Art',libraries:['General','People','Engineering','Technology','Planning','Clip art'].map(category=>({id:'usopp-'+category.toLowerCase().replaceAll(' ','-'),name:category,version:'1.0',source:'uSOPp.ai original vector artwork',license:'Original artwork; application licence',symbols:items.filter(v=>v[2]===category).map(([id,name])=>({id,name,tags:[name,category,'icon','illustration'],asset:{shape:'path',path:items.find(v=>v[0]===id)![3]}}))}))};
