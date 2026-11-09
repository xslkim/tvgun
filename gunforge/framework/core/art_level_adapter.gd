extends "level_runtime.gd"
## Generic layered 2D adapter. All gameplay remains in the shared runtime.
const Puppet=preload("puppet.gd")
const Scene=preload("art_level_scene.gd")
var puppets={}
var presentation_context={"mode":"review","lifecycle":"paused"}
var render_scene
func setup(compiled,asset_root):
	super.setup(compiled,asset_root)
	puppets.clear()
	for id in level.get("presentation",{}).get("puppets",{}):
		var definition=level.presentation.puppets[id];var animations={}
		for clip in definition.clips:animations[clip]=JSON.parse_string(FileAccess.get_file_as_string(root_path.path_join(level.resources[definition.clips[clip]].path)))
		var puppet=Puppet.new()
		puppet.open_registered(JSON.parse_string(FileAccess.get_file_as_string(root_path.path_join(level.resources[definition.character].path))),animations,images[definition.atlas]);puppets[id]=puppet
func mount(parent):
	render_scene=Scene.new();render_scene.model=self;parent.add_child(render_scene)
func set_presentation_context(mode,lifecycle):presentation_context={"mode":mode,"lifecycle":lifecycle}
func layer_items(blockers_only=false):
	var out=[]
	for id in level.get("presentation",{}).get("layers",{}):
		var layer=level.presentation.layers[id]
		if blockers_only and not layer.get("blocker",false):continue
		var item=Item.new();item.image=images[layer.resource];item.source=Rect2(Vector2.ZERO,item.image.get_size())
		if layer.has("source"):item.source=Rect2(layer.source[0],layer.source[1],layer.source[2],layer.source[3])
		item.transform=Transform2D(0,Vector2(layer.x,layer.y));item.size=Vector2(layer.width,layer.height);item.z=layer.z
		item.kind="blocker" if layer.get("blocker",false) else "";item.id="layer."+id;item.tint=Color(layer.get("tint","#ffffff"));out.append(item)
	return out
func puppet_items():
	var out=[]
	for id in entities:
		var entity=entities[id]
		if not entity.active or not entity.visible or not entity.has("puppet"):continue
		var binding=entity.puppet;var puppet=puppets[binding.rig];var target=entities[binding.target]
		var solved=target.health<=0
		var elapsed=maxf(0,(tick-target.defeated_at)/float(level.tick_hz)) if solved else float(entity.age_ticks)/level.tick_hz
		var clip=binding.idle
		if solved:
			clip=binding.success if elapsed<float(puppet.clips[binding.success].duration) else binding.rest
			if clip==binding.rest:elapsed-=float(puppet.clips[binding.success].duration)
		var pieces=puppet.items(clip,elapsed,Vector2.ZERO,entity.kind=="protected",not solved,binding.target_part,binding.target,id)
		var scale=float(entity.height)/float(puppet.rig.height)
		var base=Transform2D(0,Vector2(entity.x+entity.width*.5,entity.y+entity.height)).scaled_local(Vector2.ONE*scale)
		for item in pieces:
			item.transform=base*item.transform;item.z=float(entity.properties.get("z",20))+out.size()*.001
			if item.id==binding.target:item.id=binding.target;item.kind="primary" if target.active and not solved else "";item.generation=target.generation
			else:item.id=id;item.kind="" if entity.kind=="decoration" else entity.kind;item.generation=entity.generation
			out.append(item)
	return out
func ordered(items):
	items.sort_custom(func(a,b):return a.id<b.id if a.z==b.z else a.z<b.z)
	return items
func geometry():return ordered(super.geometry()+puppet_items()+layer_items(true))
func visual_items():
	var out=super.geometry()+puppet_items()+layer_items()
	for id in entities:
		var entity=entities[id]
		var ended=int(entity.defeated_at) if entity.defeated_at>=0 else int(entity.removed_at)
		if entity.active or ended<0 or entity.properties.get("virtual",false) or not entity.has("parts"):continue
		var age=(tick-ended)/float(level.tick_hz)
		if age>.42:continue
		for item in Motion.parts(entity,id,images,level.tick_hz):
			item.kind="";item.tint.a*=maxf(0,1-age/.42);item.transform.origin+=Vector2(0,age*32);out.append(item)
	return ordered(out)
func section_stats():
	var all_targets=[]
	var combat_sections = 0
	for section in level.get("sections",{}).values():
		if not section.targets.is_empty():
			all_targets.append_array(section.targets)
			combat_sections += 1
	var cleared=0
	for id in all_targets:
		if entities[id].health<=0:cleared+=1
	var section=level.get("sections",{}).get(current_section,{})
	var here=0
	for id in section.get("targets",[]):
		if entities[id].health<=0:here+=1
	return {"cleared":cleared,"total":all_targets.size(),"section_cleared":here,"section_total":section.get("targets",[]).size(),"section":section,"section_count":combat_sections}
