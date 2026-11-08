"""Validation for executable motion, composite alpha geometry and presentation."""
import re
def validate_scene(source,root,error):
 entities=source['entities'];resources=source['resources'];presentation=source.get('presentation',{})
 def image(id):
  if id not in resources or resources[id]['kind']!='image':raise error('missing image binding: '+id)
 def metadata(id):
  if id not in resources or resources[id]['kind']!='metadata':raise error('missing metadata binding: '+id)
 def crop(id,rect):
  from PIL import Image
  with Image.open(root/resources[id]['path']) as data:width,height=data.size
  x,y,w,h=rect
  if x<0 or y<0 or w<=0 or h<=0 or x+w>width or y+h>height:raise error('image crop outside registered resource: '+id)
 for id,entity in entities.items():
  if 'parts' in entity:
   if not entity['parts'] or set(entity.get('part_order',[]))!=set(entity['parts']):raise error('part order must name every part once: '+id)
   for part in entity['parts'].values():
    image(part['resource'])
    if 'source' in part:crop(part['resource'],part['source'])
  if 'motion' in entity:
   times=[frame['at_ms'] for frame in entity['motion']['frames']]
   if times[0]!=0 or any(a>=b for a,b in zip(times,times[1:])):raise error('motion frames need increasing milliseconds from zero: '+id)
  if 'bob' in entity and 'motion' not in entity:raise error('bobbing needs an explicit motion anchor: '+id)
  for phase in entity.get('phases',[]):
   if phase['end_ms']<=phase['start_ms']:raise error('empty motion phase: '+id)
  if 'puppet' in entity:
   binding=entity['puppet'];definition=presentation.get('puppets',{}).get(binding['rig'])
   if definition is None or binding['target'] not in entities:raise error('missing puppet rig or target: '+id)
   if any(binding[name] not in definition['clips'] for name in ['idle','success','rest']):raise error('missing puppet animation: '+id)
 for layer in presentation.get('layers',{}).values():
  image(layer['resource'])
  if 'source' in layer:crop(layer['resource'],layer['source'])
 for definition in presentation.get('puppets',{}).values():
  metadata(definition['character']);image(definition['atlas'])
  for resource in definition['clips'].values():metadata(resource)
 for topic,cue in presentation.get('sound_bindings',{}).items():
  if topic.startswith('cue.') or cue not in source['cues']:raise error('invalid sound binding: '+topic)
 for binding in presentation.get('feedback',{}).values():
  if binding not in source.get('effects',{}):raise error('missing feedback effect: '+binding)
 for id,section in source.get('sections',{}).items():
  if any(target not in entities for target in section['targets']):raise error('unknown section target: '+id)
 if presentation.get('support',{}).get('entity') not in [None,*entities]:raise error('unknown support entity')
 for resource,bounds in source.get('resource_bounds',{}).items():
  if resource not in source['initial_resources'] or bounds.get('min',-2**53)>bounds.get('max',2**53):raise error('invalid resource bounds: '+resource)
  value=source['initial_resources'][resource]
  if value<bounds.get('min',value) or value>bounds.get('max',value):raise error('initial resource outside bounds: '+resource)
 for effect in source.get('effects',{}).values():
  if not re.fullmatch(r'#[a-fA-F0-9]{6}(?:[a-fA-F0-9]{2})?',effect['color']):raise error('effect color needs explicit RGB/RGBA hex')
