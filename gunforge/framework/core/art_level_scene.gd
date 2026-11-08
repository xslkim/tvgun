extends Node2D
## Layered 2D art and deterministic presentation; owns no combat simulation.
var model
var textures={}
var font=SystemFont.new()
func _ready():font.font_names=PackedStringArray(["Microsoft YaHei","Noto Sans CJK SC"])
func _process(_delta):queue_redraw()
func label(text,point,size=28,color=Color("#e8d3ad"),centered=false):
	var at=point
	if centered:at.x-=font.get_string_size(str(text),HORIZONTAL_ALIGNMENT_LEFT,-1,size).x*.5
	draw_string_outline(font,at,str(text),HORIZONTAL_ALIGNMENT_LEFT,-1,size,4,Color(.015,.02,.03,.9*color.a))
	draw_string(font,at,str(text),HORIZONTAL_ALIGNMENT_LEFT,-1,size,color)
func texture(image):
	var id=image.get_instance_id()
	if not textures.has(id):textures[id]=ImageTexture.create_from_image(image)
	return textures[id]
func _draw():
	if model==null:return
	for item in model.visual_items():
		draw_set_transform_matrix(item.transform)
		draw_texture_rect_region(texture(item.image),Rect2(Vector2.ZERO,item.size),item.source,item.tint)
	draw_set_transform_matrix(Transform2D.IDENTITY)
	draw_intents();draw_effects();draw_hud()
func draw_intents():
	for id in model.entities:
		var entity=model.entities[id]
		if not entity.active or not entity.visible or entity.properties.get("virtual",false):continue
		var at=model.center(entity)
		if entity.stunned:
			draw_arc(at,maxf(entity.width,entity.height)*.48,0,TAU,40,Color("#dab969"),4,true)
			label(model.level.presentation.get("labels",{}).get("stunned","停顿"),at+Vector2(0,-entity.height*.45),23,Color("#e6c17a"),true)
		for phase in entity.get("phases",[]):
			if phase.id!=entity.motion_phase or entity.stunned:continue
			var progress=clampf((float(entity.age_ticks)*1000/model.level.tick_hz-phase.start_ms)/float(phase.end_ms-phase.start_ms),0,1)
			var color=Color(phase.get("color","#c9654b"));color.a=.65+.25*sin(progress*TAU*3)
			draw_arc(at,maxf(entity.width,entity.height)*(.56-.1*progress),-PI*.5,-PI*.5+TAU*progress,40,color,4,true)
			label(phase.get("label",""),at+Vector2(0,-entity.height*.48),23,color,true)
	var support=model.level.get("presentation",{}).get("support",{})
	if not support.is_empty():
		var entity=model.entities[support.entity]
		var remaining=maxf(0,(entity.next_activation-model.tick)/float(model.level.tick_hz))
		var at=model.center(entity)
		label(support.label+(" · 就绪" if remaining<=0 else " · %.1f 秒" % remaining),at+Vector2(-110,entity.height*.5+30),23,Color("#e1bd76"))
func draw_effects():
	for serial in model.active_effects:
		var instance=model.active_effects[serial];var definition=model.level.effects[instance.effect]
		var age=(model.tick-instance.start_tick)/float(model.level.tick_hz)
		var t=clampf(age*1000/definition.duration_ms,0,1)
		var at=Vector2(instance.position[0],instance.position[1]);var color=Color(definition.color);color.a*=1-t
		var radius=float(definition.get("radius",80))
		match definition.kind:
			"spark","burst":
				for i in range(12 if definition.kind=="burst" else 7):
					var angle=i*TAU/(12 if definition.kind=="burst" else 7)+int(serial)*.37
					var direction=Vector2.from_angle(angle)
					var distance=radius*(.08+t*.8)
					draw_line(at+direction*distance*.4,at+direction*distance,color,maxf(1,5*(1-t)),true)
					if definition.kind=="burst":draw_circle(at+direction*distance+Vector2(0,t*t*25),maxf(1,6*(1-t)),Color(.025,.03,.04,1-t))
				draw_arc(at,radius*t*.6,0,TAU,32,color,3,true)
			"pulse":
				draw_arc(at,maxf(1,radius*t),0,TAU,96,color,5*(1-t)+1,true)
			"link":
				var support=model.level.get("presentation",{}).get("support",{})
				if not support.is_empty():draw_line(model.center(model.entities[support.entity]),at,color,2,true)
				draw_arc(at,35+60*t,0,TAU,32,color,3,true)
			"warning":draw_arc(at,radius*(1-.5*t),0,TAU,32,color,4,true)
			"player_hit":
				var canvas=Vector2(model.level.layout.width,model.level.layout.height)
				var ink=Color(.055,.025,.025,.36*(1-t))
				for i in range(14):
					var x=(i*137+int(serial)*43)%int(canvas.x)
					draw_circle(Vector2(x,canvas.y-(i%3)*14),25+(i%4)*10,ink)
				draw_line(Vector2(15,canvas.y*.22),Vector2(15,canvas.y*.78),color,10*(1-t)+1)
				draw_line(Vector2(canvas.x-15,canvas.y*.22),Vector2(canvas.x-15,canvas.y*.78),color,10*(1-t)+1)
				label(definition.get("label",""),Vector2(canvas.x*.5,canvas.y*.72),40,color,true)
		if definition.kind!="player_hit" and definition.has("label"):label(definition.label,at+Vector2(0,-20-t*40),26,color,true)
func draw_hud():
	var presentation=model.level.presentation
	var canvas=Vector2(model.level.layout.width,model.level.layout.height)
	var stats=model.section_stats();var section=stats.section
	draw_rect(Rect2(0,0,canvas.x,80),Color(.018,.025,.045,.8))
	label(presentation.get("title",""),Vector2(25,36),30)
	if not section.is_empty():
		label("第 %d / %d %s · %s" % [section.index,stats.section_count,presentation.get("labels",{}).get("section_unit","段"),section.title],Vector2(25,67),25)
		label("本段 %d / %d · %s %d / %d" % [stats.section_cleared,stats.section_total,presentation.get("labels",{}).get("progress","完成"),stats.cleared,stats.total],Vector2(canvas.x*.47,48),27,Color("#dfbc77"),true)
	var resources=[]
	for field in model.level.get("hud",[]):resources.append(field.label+" "+str(int(model.resources[field.resource])))
	# Right-align resource text without depending on game-specific counter names.
	var resource_text="  ".join(resources)
	var width=font.get_string_size(resource_text,HORIZONTAL_ALIGNMENT_LEFT,-1,26).x
	label(resource_text,Vector2(canvas.x-width-25,45),26)
	if not section.is_empty():label(section.get("hint",""),Vector2(canvas.x*.5,canvas.y-22),25,Color("#dbc8a8"),true)
	var context=model.presentation_context
	if context.mode=="player" and context.lifecycle=="ready":
		draw_rect(Rect2(Vector2.ZERO,canvas),Color(.015,.02,.04,.72))
		label(presentation.get("title",""),Vector2(canvas.x*.5,canvas.y*.34),68,Color("#ebd8b0"),true)
		label(presentation.get("subtitle",""),Vector2(canvas.x*.5,canvas.y*.43),34,Color("#cfa773"),true)
		label(presentation.get("instructions",""),Vector2(canvas.x*.5,canvas.y*.58),29,Color("#dfd0b4"),true)
		label("Enter 开始 · 鼠标 / 光枪射击 · R 换弹",Vector2(canvas.x*.5,canvas.y*.72),30,Color("#e3bd76"),true)
	elif model.phase=="result":
		draw_rect(Rect2(Vector2.ZERO,canvas),Color(.02,.025,.045,.65))
		label(presentation.get("labels",{}).get("result_success","完成") if model.result=="clear" else presentation.get("labels",{}).get("result_failure","失败"),Vector2(canvas.x*.5,canvas.y*.4),62,Color("#e7c994"),true)
		label("%s %d / %d · Enter 再试一次" % [presentation.get("labels",{}).get("progress","完成"),stats.cleared,stats.total],Vector2(canvas.x*.5,canvas.y*.54),32,Color("#e0c59e"),true)
