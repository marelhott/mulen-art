"""Prepare reviewed local images. Originals are never modified."""
import hashlib, json, io
from pathlib import Path
from PIL import Image, ImageOps, ImageCms
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/research/tuymans'
# Captions describe visible content; no identity or artwork title is inferred.
CAPTIONS = '''
0|a dark tower behind pale bare branches
1|an ornate pale chandelier against a dark background
2|the back of a person's head with short reddish hair
3|a standing person in profile beside a window with horizontal blinds
4|a patterned moth with spread wings against a pale ground
5|a pale face looking forward with a faint smile
6|a close frontal portrait of a young person with dark hair
7|several pale figures standing behind a railing
9|a small standing figure beside a dark wall and a green lawn
10|a frontal portrait of a man wearing glasses, a suit and a tie
11|a pale aerial view of winding roads through a snowy landscape
12|a man's head in profile against a mottled background
15|dark horizontal shelves against a pale wall
16|a pale cloud floating above a low band of vegetation
17|an indistinct pale head seen in profile
18|a pale airplane seen from below against a flat sky
19|a dark oval head against a pale background
20|an empty chair beside a vertically striped wall
21|a close portrait of a man with short hair and a moustache
22|a cropped figure wearing a striped swimsuit with one hand on the hip
24|a seated young man in a pale collared shirt looking forward
26|the cropped torso of a figure in a pale garment with dark seams
27|three hanging round objects suspended from thin vertical lines
28|an empty bedroom with a blue wardrobe, a chair, drawers and a bed
29|a close view of pale irregular cracked stone slabs
30|small figures standing in an open pale landscape
31|a pale anatomical skeleton against a light background
32|a close view of a man's face with a moustache looking sideways
33|a green cross set into a pale tiled floor
34|a solitary figure beside a large tree and water
35|a softly defined pale oval with vertical stripes on a gray background
36|a close view of a faint face in profile
37|two rectangular gridded panels standing in an empty room
38|a pale seated figure surrounded by dark foliage
39|a small figure beside a yellow vehicle and green vegetation
41|a frontal portrait of a man wearing rectangular glasses
42|a large arched window in a brick facade
44|a seated man wearing glasses in a bright interior
45|a tall sailing ship with dark square sails
46|a close portrait of a woman looking forward
47|a bright green flower with long striped petals against a dark background
48|an ornamental flowering plant with leaves and small blossoms
50|small figures walking beneath a bare tree beside a pale building
51|a pale figure seated on a chair beside a table
52|a young person wearing a military cap and uniform
53|an empty room with a wooden desk, a chair and shelves
54|the back of a balding man's head
55|a person seen from above with head lowered against a blue background
56|an empty circular table surrounded by pale covered chairs
57|a pale circular platform or island on a blue-gray ground
58|a pale bald face with reddish eyes against a dark background
61|a round orange-red container against a dark background
62|a blue silhouette of a walking person carrying a large round object
63|a corner lined with pale yellow paneled doors
64|a solitary swimmer among dark ripples of water
67|a cropped pale torso in patterned swimwear
68|a faint suspended figure or ornament against a green ground
69|a tiny row of pale figures around a long table in a dark room
70|a close view of a man's face with a long nose
71|a man's face beneath the brim of a hat
72|a brick fireplace with dark objects on its mantel
73|dense tangled vegetation and branches in a wooded scene
74|a pale round light hanging from a thin cord above a bed
75|a dense ornamental textile pattern with irregular colored shapes
76|a patterned storefront or interior behind a grid of window frames
77|two pale hands against a light background
78|a close view of a face partly hidden behind a pale horizontal edge
79|a close view of a man's face with dark eye sockets
80|a snowy rocky landscape with a dark hill in the distance
81|pale tangled grasses illuminated against a dark background
82|a crumpled pale yellow paper object with an orange-red patch
83|a child's head against a densely patterned background
84|a solitary large building in a flat pale landscape
85|a close cropped face with a broad toothy smile
86|a faint pale flying bird against an almost white background
87|a close cropped frontal face with dark eyes and lips
88|the cropped torso of a figure wearing a dark ornate robe
89|a standing figure in a red jacket beside outdoor stairs
90|tangled branches and rounded shapes in a wooded scene
92|two dark figures standing in a rocky mountainous landscape
93|a vase holding long leaves and stems on a table
94|an indistinct pale horizontal form against a blue-gray ground
95|a slender green plant stem with small pale leaves
96|pigeons scattered across a pale paved square
97|a close view of a reflective vehicle headlight
98|a tree trunk and dense foliage with scattered pale highlights
100|a seated woman in a blue dress casting a dark shadow
101|a person with pale hair seated inside a dark vehicle
102|a frontal portrait of a young boy with short hair
103|irregular rounded rock formations in pale brown and gray
104|two formally dressed figures dancing on a patterned floor
105|a pale textile densely covered in small reddish marks
106|scattered dark and red circles against a pale green ground
107|a close view of a green flower bud
108|a bare-chested man seen from the side against a striped wall
109|a faint frontal portrait of a boy on a mottled pale ground
110|several faces visible through the curved windows of a vehicle
111|a tightly cropped pair of faces close together
112|a round pale target or dish with a red center against a dark red ground
113|a pile of pale round vegetables with a few green stems against a dark background
114|a pale ornate castle with many narrow towers against a dark sky
115|a pale rabbit in profile surrounded by leaves
116|a tightly cropped view of a man's eye and nose
117|a tightly cropped frontal face with a dark mouth and nose
118|an outstretched dark hand on a yellow ground
119|two raised hands above a pale garment
120|a pale round object surrounded by small reddish spots
121|a woman's pale face looking upward against a dark background
122|a pale rounded mechanical object on a table
123|a view down onto houses, trees, gardens and a narrow road
124|a close view of a brown object with pale straps, rings and buckles
125|a pale seated figure with folded arms inside a vehicle
'''
EXCLUDE = {8:'graphic line drawing; outside painting baseline',13:'graphic line drawing; outside painting baseline',14:'photographic-looking mask; uncertain medium',23:'line drawing and collage',25:'high-contrast graphic trees; outside painting baseline',40:'strong cracked-surface artifact',43:'crowded scene; defer for separate review',49:'graphic line drawing; outside painting baseline',59:'detail of same face as 58',60:'same work as 58 with extra border',65:'two separate artworks in one reproduction',66:'several inset reproductions with labels',91:'explicit Image-Super-Resolution source; same composition as 17',99:'graphic pattern; defer for separate review'}

def main():
 rows=json.loads((OUT/'review-candidates.json').read_text())
 captions={int(line.split('|',1)[0]):line.split('|',1)[1] for line in CAPTIONS.strip().splitlines()}
 assert set(captions)|set(EXCLUDE)==set(range(len(rows)))
 dest=OUT/'dataset-v2'; dest.mkdir(exist_ok=True)
 manifest=[]
 # Keep related close-up portraits together to prevent validation leakage.
 related={70:'historic-portrait-group',116:'historic-portrait-group',117:'historic-portrait-group',5:'face-series',87:'face-series'}
 for i,r in enumerate(rows):
  if i in EXCLUDE:
   manifest.append({**r,'index':i,'split':'excluded','reason':EXCLUDE[i]}); continue
  group=related.get(i,r['sha256']); split='validation' if int(hashlib.sha256(group.encode()).hexdigest()[:8],16)%8==0 else 'train'
  folder=dest/split; folder.mkdir(exist_ok=True)
  name=f'tuy_{i:03d}'
  with Image.open(r['path']) as im:
   im=ImageOps.exif_transpose(im)
   profile=im.info.get('icc_profile')
   if profile:
    im=ImageCms.profileToProfile(im,ImageCms.ImageCmsProfile(io.BytesIO(profile)),ImageCms.createProfile('sRGB'),outputMode='RGB')
   else:
    im=im.convert('RGB')
   # Bound decoded image size, never upscale or add synthetic details.
   im.thumbnail((2048,2048),Image.Resampling.LANCZOS)
   im.save(folder/(name+'.png'))
   width,height=im.size
  caption='mvhpaint, '+captions[i]
  (folder/(name+'.txt')).write_text(caption+'\n')
  manifest.append({**r,'index':i,'split':split,'caption':caption,'prepared_size':[width,height],'prepared':str(folder/(name+'.png'))})
 (dest/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
 (OUT/'POPiSKY_KONTROLA.md').write_text('# Popisky datasetu v2\n\nVizuálně posouzené celé reprodukce. Originály beze změn; bez AI zvětšování. Výběr je výchozí experiment, nikoli ověřené autorství každého zdroje.\n\n'+'\n'.join(f"- {r['index']:03d} [{r['split']}] {r.get('caption',r.get('reason'))}" for r in manifest)+'\n')
 from collections import Counter
 print(Counter(r['split'] for r in manifest))
if __name__=='__main__': main()
