"""Prepare a reserve set of small, visually reviewed originals at native/lower resolution.
This set is NOT automatically added to a running training experiment.
"""
import hashlib,io,json
from pathlib import Path
from PIL import Image,ImageCms,ImageOps
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/research/tuymans'
CAPTIONS='''
0|a large round mirror or window on a pale wall above small dark objects
7|a dim empty passenger compartment with a row of seats
14|a pale tree trunk rising from softly defined woodland ground
15|two faint candle-like upright forms against a blue-gray ground
17|a bright pale circular form floating against a gray ground
19|a faint blue rectangular display or reflection in a dark interior
21|a small dark piece of meat on a pale pink ground
22|the back of a person's head and neck in shadow
24|a pair of long pale gloves hanging against a divided background
27|a pale shallow dish with a dark irregular rim
31|soft pale hills beneath a gray cloudy sky
33|a pale city skyline with narrow towers under a blue-gray sky
34|an extremely pale face seen in profile
37|a faint upright figure above a dark horizontal band
40|two small pale figures riding horses against a muted green ground
41|a pale bald man in round dark glasses
43|a group of pale buildings with dark roof shapes
44|faint diamond shapes on a pale patterned floor
45|a dark sloping surface with diagonal lines and scattered pale marks
48|an empty cream-colored room with dark openings and ceiling fixtures
51|a man's downcast face above a dark suit and tie
52|a small isolated oval face with yellow eyes on a pale ground
53|a tightly cropped pale face with almost erased features
54|a dim green room with a bed, a lamp and small furniture
55|a man in a pale jacket and dark tie looking to one side
56|two overlapping dark figures in front of a pale rectangular opening
59|a faint glass and several small round objects on a pale tabletop
60|an empty pale waiting room with benches around a dark-topped pedestal
61|a dark triangular form on a mottled gray ground
63|a blurred row of small figures in orange clothing
64|clusters of pale rounded forms against a mottled blue-gray background
65|a soft dark silhouette behind pale vertical blinds
66|a vertical chain of pale rings against a reflective gray surface
67|a pale figure with a white head covering and beard beside dark vertical panels
69|a translucent curved yellow form against a pale yellow ground
71|three small dark hooded figures on a pale flat landscape
72|a pale ornate interior with arches and columns
74|a soft bright oval light against a gray-brown ground
75|faint glasses and small vessels on a pale tabletop
78|an empty dark building interior with exposed structural frames
79|an empty orange-pink bedroom with a chair and a curtained window
80|vertical curtains or blinds in a dark room
81|a pale bedroom corner with curtains, a bed and dark blue trim
82|a pale sofa in front of striped curtains
84|a dark seated figure fading into a pale blue-gray ground
85|an almost erased pale face with dark hair and small glasses
88|pale sculptural forms and a small seated figure in an indistinct setting
89|pale figures and curved forms in a wooded setting
90|a pale pot holding a small flowering plant
93|dark wooden beams crossing a pale ceiling
95|a tightly cropped pale face in profile with a blue eye
103|a cropped leg beneath a gray skirt
104|a pale round form near a dark horizontal edge on a green-gray ground
105|a small open angular box on a dark ground
106|a very faint pale bird-like form against an almost white ground
107|a pale cylindrical object with a large dark circular opening
108|several pale cylindrical towers beside a small dark figure
115|a softly lit round opening in a dark wall
120|a glowing red electric heater against a dark blue-gray background
121|an almost white office interior with a desk and pale chairs
122|a faint portrait of a man wearing dark rectangular glasses
125|overlapping translucent circular and oval shapes in pale green
126|two pale older men facing one another in an interior
130|a pale green curved oval form above a vertical dark band
132|a pale green interior with a small table and ornate chairs
'''

def main():
    rows=json.loads((OUT/'review-low-candidates.json').read_text())
    main=json.loads((OUT/'dataset-v2/manifest.json').read_text())
    captions={int(x.split('|',1)[0]):x.split('|',1)[1] for x in CAPTIONS.strip().splitlines()}
    dest=OUT/'soft-originals-reserve';dest.mkdir(exist_ok=True)
    manifest=[]
    for i,caption in captions.items():
        r=rows[i]
        # Conservative leakage guard: defer visually similar crops/versions already in the main set.
        matches=[a for a in main if a['split']!='excluded' and
                 abs(a['width']/a['height']-r['width']/r['height'])<.08 and
                 (int(a['dhash'],16)^int(r['dhash'],16)).bit_count()<=8]
        if matches:
            manifest.append({**r,'index':i,'split':'deferred_possible_duplicate',
                             'possible_matches':[a['path'] for a in matches]});continue
        split='validation' if int(hashlib.sha256(r['sha256'].encode()).hexdigest()[:8],16)%8==0 else 'train'
        folder=dest/split;folder.mkdir(exist_ok=True);name=f'soft_{i:03d}'
        with Image.open(r['path']) as im:
            im=ImageOps.exif_transpose(im);profile=im.info.get('icc_profile')
            if profile:
                im=ImageCms.profileToProfile(im,ImageCms.ImageCmsProfile(io.BytesIO(profile)),ImageCms.createProfile('sRGB'),outputMode='RGB')
            else:im=im.convert('RGB')
            # Keep original pixel dimensions. A later 512px bucket may downsample, never upscale.
            im.save(folder/(name+'.png'));size=im.size
        caption='mvhpaint, '+caption
        (folder/(name+'.txt')).write_text(caption+'\n')
        manifest.append({**r,'index':i,'split':split,'caption':caption,'prepared_size':size,
                         'prepared':str(folder/(name+'.png'))})
    (dest/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    from collections import Counter
    print(Counter(r['split'] for r in manifest))
    print('Deferred:',[(r['index'],r['possible_matches']) for r in manifest if r['split'].startswith('deferred')])
if __name__=='__main__':main()
