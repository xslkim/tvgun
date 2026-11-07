"""Prepare the two Paper Lantern City residents for the native art2d build."""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'pipeline/split'))
from prepare import isolate, write_json


PROFILES = {
    'vendor': {
        'label': '卖糖葫芦居民', 'wrists': [[76, 153], [101, 181]],
        'ankles': [[78.28, 183.31], [78.02, 184.40]],
        'sleeve_end': [151, 177], 'hand_start': [144, 168],
        'prop_grip': [109, 185], 'prop_pivot': [20, 163], 'prop_angle': -16,
        'grip_thumb': [[89, 153], [115, 152], [131, 171], [132, 197],
                       [120, 200], [114, 196], [111, 191], [108, 182],
                       [101, 181], [95, 176], [91, 170], [88, 161]],
        'collar': [[133, 47], [210, 47], [212, 74], [197, 82], [151, 83], [133, 73]],
        'upper_angles': [-108, -78], 'elbow_angles': [-7, 9],
    },
    'video': {
        'label': '录像厅老板', 'wrists': [[87, 133], [95, 174]],
        'ankles': [[80.54, 192.34], [84.62, 188.05]],
        'sleeve_end': [134, 159], 'hand_start': [126, 151],
        'prop_grip': [99, 185], 'prop_pivot': [12, 24], 'prop_angle': 12,
        'grip_thumb': [[77, 140], [113, 140], [119, 159], [117, 176],
                       [114, 188], [110, 194], [104, 198], [98, 197],
                       [94, 193], [93, 186], [93, 177], [89, 171],
                       [83, 166], [79, 161], [76, 153]],
        'collar': [[140, 46], [245, 45], [263, 77], [256, 98], [206, 91], [158, 73]],
        'upper_angles': [-103, -80], 'elbow_angles': [-8, 11],
    },
}


def rgba(path):
    with Image.open(path) as image:
        return image.convert('RGBA')


def axis(start, end):
    return math.degrees(math.atan2(start[1] - end[1], end[0] - start[0]))


def offset(point, angle, length):
    a = math.radians(angle)
    return [point[0] + math.cos(a) * length, point[1] + math.sin(a) * length]


def bone_track(*keys):
    return [[t, 0, 0, angle] for t, angle in keys]


def shift_track(*keys):
    return [[t, x, y, 0] for t, x, y in keys]


def clip(label, duration, tracks, **options):
    return dict(label=label, duration=duration, tracks=tracks, **options)


def facial(*keys):
    return [{'time': t, 'variant': variant} for t, variant in keys]


def animations(role):
    amplitude = 1 if role == 'vendor' else .83
    return {
        'idle': clip('站立呼吸', 2.4, {
            'hip': shift_track((0, 0, 0), (1.2, .8, -2.4), (2.4, 0, 0)),
            'spine': bone_track((0, 0), (1.2, -1.5), (2.4, 0)),
            'head': bone_track((0, 0), (1.2, 1.2), (2.4, 0)),
        }, loop=True),
        'walk': clip('行走', 1.4, {
            'hip': shift_track((0, 0, -7), (.35, 1, -4), (.7, 0, -7), (1.05, -1, -4), (1.4, 0, -7)),
            'spine': bone_track((0, -1.5), (.35, -3.2), (.7, -1.5), (1.05, -3.2), (1.4, -1.5)),
            'upper_arm_near': bone_track((0, -7), (.7, 9), (1.4, -7)),
            'forearm_near': bone_track((0, -2), (.7, -8), (1.4, -2)),
            'upper_arm_far': bone_track((0, 3), (.7, -3), (1.4, 3)),
            'head': bone_track((0, 0), (.7, 2), (1.4, 0)),
        }, loop=True, gait={'stride': 68 if role == 'vendor' else 61, 'duty': .63, 'lift': 15 * amplitude}),
        'peek': clip('探身观察', 2.8, {
            'hip': shift_track((0, 0, 0), (.8, 6, -4), (1.65, 6, -4), (2.8, 0, 0)),
            'spine': bone_track((0, 0), (.8, -8), (1.65, -8), (2.8, 0)),
            'head': bone_track((0, 0), (.95, 4), (1.65, 4), (2.8, 0)),
        }, attachment_keys={'head_relaxed': facial((.5, 'distress'), (2.42, ''))}),
        'startle': clip('受惊回缩', 1.8, {
            'hip': shift_track((0, 0, 0), (.25, -7, -7), (.53, -4, -3), (1.8, 0, 0)),
            'spine': bone_track((0, 0), (.22, 7), (.46, 3), (1.8, 0)),
            'head': bone_track((0, 0), (.17, 5), (.45, -3), (1.8, 0)),
            'upper_arm_near': bone_track((0, 0), (.26, -15), (.56, -8), (1.8, 0)),
            'forearm_near': bone_track((0, 0), (.28, -23), (.62, -9), (1.8, 0)),
        }, attachment_keys={'head_relaxed': facial((.12, 'distress'), (1.53, ''))}),
        'wave_for_help': clip('求助与收手', 4.5, {
            'hip': shift_track((0, 0, 0), (.58, -2, -1.8), (1.1, 0, 0), (2.8, 0, 0), (4.5, 0, 0)),
            'spine': bone_track((0, 0), (.96, 4), (2.8, 4), (4.16, 0)),
            'upper_arm_near': bone_track((0, 0), (.3, -7), (.73, -50), (1.12, -67), (2.72, -67),
                                         (3.15, -46), (3.65, -14), (4.17, 0)),
            'forearm_near': bone_track((0, 0), (.3, -4), (.73, -47), (1.12, -75), (1.43, -85), (1.74, -72),
                                       (2.04, -85), (2.36, -72), (2.72, -75), (3.2, -49), (3.64, -13), (4.17, 0)),
            'hand_near': bone_track((0, 0), (1.12, 0), (1.43, -7), (1.74, 7), (2.04, -7),
                                    (2.36, 7), (2.72, 0), (4.5, 0)),
        }, attachment_keys={'head_relaxed': facial((0, 'distress')),
                            'hand_near': facial((.84, 'open_palm'), (3.18, ''))}),
        'struggle': clip('附墨挣扎', 3, {
            'hip': shift_track((0, 0, 0), (.7, -3, -4), (1.45, 3, -5), (2.18, -2, -3), (3, 0, 0)),
            'spine': bone_track((0, 0), (.7, 5), (1.45, -5), (2.18, 3), (3, 0)),
            'head': bone_track((0, 0), (.63, -5), (1.45, 4), (2.18, -4), (3, 0)),
            'upper_arm_near': bone_track((0, -14), (.65, -24), (1.45, -18), (2.14, -25), (3, -14)),
            'forearm_near': bone_track((0, -6), (.65, -13), (1.45, -9), (2.14, -11), (3, -6)),
            'upper_arm_far': bone_track((0, 7), (.7, 14), (1.45, 9), (2.18, 13), (3, 7)),
        }, loop=True, attachment_keys={'head_relaxed': facial((0, 'distress')), 'rescue_ink': [{'time':0, 'visible':True}]}),
        'rescued_bounce': clip('获救与落地', 2.2, {
            'hip': shift_track((0, 0, 0), (.32, 0, -12), (.55, 0, -2), (.78, 0, 0), (1.13, 0, -6),
                               (1.24, 0, -11), (1.67, 0, 0)),
            'spine': bone_track((0, 0), (.32, -6), (.75, 3), (1.2, -5), (1.67, 0)),
            'upper_arm_near': bone_track((0, -14), (.31, -6), (.74, -22), (1.23, -7), (1.67, 0)),
            'forearm_near': bone_track((0, -6), (.31, -13), (.74, -20), (1.67, 0)),
            'upper_arm_far': bone_track((0, 7), (.74, 10), (1.67, 0)),
        }, rise=[[0,0],[.55,0],[.83,23*amplitude],[1.13,0],[2.2,0]], contacts=[[0,.55],[1.13,2.2]],
           events=[{'id':'freed','time':.2},{'id':'takeoff','time':.55},{'id':'land','time':1.13}],
           attachment_keys={'head_relaxed': facial((0,'distress'),(1.24,'')),
                            'rescue_ink':[{'time':0,'visible':True},{'time':.2,'visible':False}]}),
        'thank': clip('点头致谢', 2.6, {
            'hip': shift_track((0, 0, 0), (.77, 3, -6), (1.35, 3, -6), (2.6, 0, 0)),
            'spine': bone_track((0, 0), (.72, -10), (1.36, -10), (2.6, 0)),
            'head': bone_track((0, 0), (.9, -10), (1.27, -9), (2.45, 0)),
            'upper_arm_near': bone_track((0, 0), (.8, 18), (1.35, 18), (2.5, 0)),
            'forearm_near': bone_track((0, 0), (.8, -13), (1.35, -13), (2.5, 0)),
        }),
    }


def prepare_character(cache, role):
    p = PROFILES[role]
    identifier = 'paper_lantern_' + role
    folder = ROOT / 'assets' / identifier / 'concept'
    folder.mkdir(parents=True, exist_ok=True)
    old = cache / role
    model = json.loads((old / 'puppet.json').read_text(encoding='utf-8'))
    nodes = {node['id']: node for node in model['parts']}
    files = {key: old / node['file'] for key, node in nodes.items()}
    parts = {key: rgba(path) for key, path in files.items()}
    extra = json.loads((old / 'attachments_v3/attachments.json').read_text(encoding='utf-8'))
    for name in ['head', 'palm']:
        key = 'distress' if name == 'head' else 'palm'
        files[key] = old / 'attachments_v3' / extra[name]['file']
        parts[key] = rgba(files[key])
    files['ink'] = cache / 'ink_blobs/blob_00.png'
    parts['ink'] = rgba(files['ink'])
    reference = cache / (role + '_concept_a1.png')
    ref = rgba(reference)

    # Keep source pieces together with their original pixels. Layout performs the cuts.
    sheet = Image.new('RGBA', (ref.width + 24 + 1280, max(ref.height, 1320)))
    sheet.paste(ref, (0, 0))
    boxes = {}
    x, y, row_height = ref.width + 24, 12, 0
    for key, im in parts.items():
        if x + im.width + 12 > sheet.width:
            x, y, row_height = ref.width + 24, y + row_height + 12, 0
        sheet.paste(im, (x, y))
        boxes[key] = [x, y, x + im.width, y + im.height]
        x += im.width + 12
        row_height = max(row_height, im.height)
    if y + row_height > sheet.height:
        raise ValueError('Source sheet bounds exceeded')

    scale = .675 if role == 'vendor' else .661
    layout = {'reference': [0,0,ref.width,ref.height], 'parts': {}}
    dimensions = {}

    def part(name, key, pivot, polygon=None, subtract=False, crop_y=None, factor=scale):
        box = boxes[key].copy()
        left, top = box[:2]
        if crop_y:
            box[1] = top + crop_y[0]
            box[3] = top + crop_y[1]
        mask = [[left + u, top + v] for u,v in polygon] if polygon else None
        cropped, trim = isolate(sheet, box, None, mask, subtract, with_bounds=True)
        u = (left + pivot[0] - box[0] - trim[0]) / cropped.width
        v = (top + pivot[1] - box[1] - trim[1]) / cropped.height
        if not (0 <= u <= 1 and 0 <= v <= 1):
            raise ValueError(f'{name}: pivot {u:.3f}, {v:.3f} outside trimmed crop')
        layout['parts'][name] = {'crop':box, 'anchor':[u,v]}
        if mask:
            layout['parts'][name].update(polygon=mask,subtract=subtract)
        dimensions[name] = [cropped.width*factor, cropped.height*factor]

    leg_data = []
    for i, side in enumerate(['l','r']):
        thigh, shin = nodes['thigh_'+side], nodes['shin_'+side]
        ankle = p['ankles'][i]
        lengths = [math.dist(thigh['pivot'],shin['attach'])*scale,math.dist(shin['pivot'],ankle)*scale]
        sole_y = parts['shin_'+side].getchannel('A').point(lambda a:255 if a>100 else 0).getbbox()[3]
        leg_data.append((thigh,shin,ankle,lengths,(sole_y-ankle[1])*scale))
    hip_src = [(leg_data[0][0]['attach'][i]+leg_data[1][0]['attach'][i])/2 for i in range(2)]
    hip_y = min(sole + sum(lengths)*.994 for _,_,_,lengths,sole in leg_data)

    def body_point(xy):
        return [(xy[0]-hip_src[0])*scale,hip_y+(hip_src[1]-xy[1])*scale]

    neck = body_point(nodes['head']['attach'])
    chest = body_point([hip_src[0],108])
    spine_source = [hip_src[0], hip_src[1]-57]
    bones = [['spine','hip',*body_point(spine_source),90,52],['chest','spine',*chest,90,35],
             ['neck','chest',*neck,90,15],['head','neck',*neck,90,60]]
    limits = [['spine',-12,10],['head',-13,9]]
    attachments = []

    def attach(bone, name, image_axis=0, variants=None):
        entry = [bone,name,*dimensions[name],image_axis]
        if variants:
            entry.append(variants)
        attachments.append(entry)

    legs = []
    for i, suffix in [(1,'far'),(0,'near')]:
        thigh, shin, ankle, lengths, sole = leg_data[i]
        source_shin, source_thigh = shin['id'],thigh['id']
        origin = body_point(thigh['attach'])
        foot = [origin[0] + (8 if i else -3), sole]
        legs.append(dict(suffix=suffix,origin=origin,foot=foot,lengths=lengths,sign=-1,phase=i*.5,sole=[7,-sole]))
        cut = round(ankle[1])
        part('shoe_'+suffix,source_shin,ankle,crop_y=[cut-13,parts[source_shin].height])
        part('shin_'+suffix,source_shin,shin['pivot'],crop_y=[0,cut-3])
        part('thigh_'+suffix,source_thigh,thigh['pivot'])
        attach('foot_'+suffix,'shoe_'+suffix)
        attach('lower_leg_'+suffix,'shin_'+suffix,axis(shin['pivot'],ankle))
        attach('upper_leg_'+suffix,'thigh_'+suffix,axis(thigh['pivot'],shin['attach']))

    for i,suffix in [(1,'far'),(0,'near')]:
        side = ['l','r'][i]
        upper, lower = nodes['upper_arm_'+side], nodes['forearm_'+side]
        u, v = upper['id'], lower['id']
        wrist = p['wrists'][i]
        upper_axis = axis(upper['pivot'],lower['attach'])
        lower_axis = axis(lower['pivot'],wrist)
        upper_a = p['upper_angles'][i]
        lower_a = upper_a + p['elbow_angles'][i]
        shoulder = body_point(upper['attach'])
        upper_len = math.dist(upper['pivot'],lower['attach'])*scale
        lower_len = math.dist(lower['pivot'],wrist)*scale
        elbow = offset(shoulder,upper_a,upper_len)
        hand = offset(elbow,lower_a,lower_len)
        bones.extend([['shoulder_'+suffix,'chest',*shoulder,0,0],['upper_arm_'+suffix,'shoulder_'+suffix,*shoulder,upper_a,upper_len],
                      ['forearm_'+suffix,'upper_arm_'+suffix,*elbow,lower_a,lower_len],['hand_'+suffix,'forearm_'+suffix,*hand,lower_a,21]])
        limits.extend([['upper_arm_'+suffix,-70 if not i else -5,22],
                       ['forearm_'+suffix,-91 if not i else -3,3 if not i else 4,-1 if not i else 1],
                       ['hand_'+suffix,-8,8]])
        part('upper_'+suffix,u,upper['pivot'])
        part('sleeve_'+suffix,v,lower['pivot'],crop_y=[0,p['sleeve_end'][i]])
        if i:
            grip = p['prop_grip']
            dx,dy = (grip[0]-wrist[0])*scale, (wrist[1]-grip[1])*scale
            da = math.radians(lower_a-lower_axis)
            grip_world = [hand[0]+dx*math.cos(da)-dy*math.sin(da),hand[1]+dx*math.sin(da)+dy*math.cos(da)]
            bones.append(['held_prop','hand_far',*grip_world,p['prop_angle'],0])
            hand_crop = [p['hand_start'][i], parts[v].height]
            part('hand_far', v, wrist, crop_y=hand_crop)
            part('hand_far_front', v, wrist, polygon=p['grip_thumb'], crop_y=hand_crop)
            part('held_object','prop',p['prop_pivot'])
            # The original palm provides a continuous underlay. Only the thumb
            # returns in front, on the same wrist and along its drawn contour.
            attach('hand_far','hand_far',lower_axis)
            attach('held_prop','held_object')
            attach('hand_far','hand_far_front',lower_axis)
            attach('forearm_far','sleeve_far',lower_axis)
            attach('upper_arm_far','upper_far',upper_axis)
        else:
            near_axes = (upper_axis,lower_axis)
            part('hand_near',v,wrist,crop_y=[p['hand_start'][i],parts[v].height])
            part('hand_open','palm',extra['palm']['pivot'])

    part('torso_shell','torso',spine_source,p['collar'],subtract=True)
    part('collar_front','torso',nodes['head']['attach'],p['collar'])
    part('head_relaxed','head',nodes['head']['pivot'])
    part('head_distress','distress',extra['head']['pivot'])
    attach('spine','torso_shell',90)
    ink_diameter = 98 if role=='vendor' else 152
    ink_crop = parts['ink'].getchannel('A').point(lambda a:255 if a>30 else 0).getbbox()
    part('rescue_ink','ink',[(ink_crop[i]+ink_crop[i+2])/2 for i in range(2)],factor=ink_diameter/(ink_crop[2]-ink_crop[0]))
    bones.append(['ink_anchor','spine',*body_point(model['ink_anchor']),90,0])
    attach('ink_anchor','rescue_ink',90)
    attach('head','head_relaxed',90,{'distress':{'part':'head_distress','size':dimensions['head_distress'],'imageAxis':90}})
    attach('neck','collar_front',90)
    upper_axis, lower_axis = near_axes
    attach('hand_near','hand_near',lower_axis,{'open_palm':{'part':'hand_open','size':dimensions['hand_open'],'imageAxis':90}})
    attach('forearm_near','sleeve_near',lower_axis)
    attach('upper_arm_near','upper_near',upper_axis)

    spec = dict(id=identifier,label=p['label'],prototype='humanoid',height=512,hip=[0,hip_y,0],
                bones=bones,legs=legs,attachments=attachments,limits=limits,hiddenParts=['rescue_ink'],
                animation=animations(role),view='right_facing_three_quarter',role='civilian_npc_or_hostage')
    if role == 'vendor':
        spec['worldAngles'] = {'held_prop':p['prop_angle']}
    sheet.save(folder/'raw.png')
    write_json(folder/'layout.json',layout)
    write_json(folder/'rig_layout.json',spec)
    write_json(folder/'manifest.json',{
        'source':'Existing Paper Lantern City GPT resident artwork, lossless source sheet assembly',
        'source_files':{k:{'path':str(f),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for k,f in {**files,'design':reference}.items()},
        'source_request_ledger':'gunforge/games/g01/reports/art/T05/calls.json',
        'model_version':None,'seed':None,'new_generation_calls':0,
        'rights':'Existing project character sources. Original prompts and provider metadata are in the T05 call ledger.',
    })
    (folder/'CARD.md').write_text(
        f'# {p["label"]}\n\n人形 NPC / 人质。右向三分之四机位，绑定单位像素，标准高度 512。'
        '近侧为画面左侧的解剖右侧，远侧持物。纸纹、服装、担忧表情及持物图源来自 T05。\n\n'
        '手、鞋、领口和道具独立切件。远臂位于躯干后，近臂位于躯干前。领口覆盖颈根。'
        '行走以地速和支撑脚 IK 配合。八个动作见 rig_layout.json。\n',encoding='utf-8')
    print(identifier, len(layout['parts']), 'parts')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache',type=Path,default=Path('D:/gunforge_cache/g01/T05'))
    args = parser.parse_args()
    for role in PROFILES:
        prepare_character(args.cache,role)
