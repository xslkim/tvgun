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
			label(model.level.get("presentation",{}).get("labels",{}).get("stunned","停顿"),at+Vector2(0,-entity.height*.45),23,Color("#e6c17a"),true)
		for phase in entity.get("phases",[]):
			if phase.id!=entity.motion_phase or entity.stunned:continue
			var progress=clampf((float(entity.age_ticks)*1000/model.level.tick_hz-phase.start_ms)/float(phase.end_ms-phase.start_ms),0,1)
			var color = Color(phase.get("color","#c9654b"))
			var radius = maxf(entity.width,entity.height) * .55 * float(entity.get("pose_scale",1))
			draw_arc(at,radius,0,TAU,48,Color("#321e24"),12,true)
			draw_arc(at,radius,0,TAU,48,Color(color,.55),4,true)
			if progress>0.0:
				draw_arc(at,radius,-PI*.5,-PI*.5+TAU*progress,48,color,8,true)
			var caption = str(phase.get("label",""))
			if not caption.is_empty():
				label(caption,Vector2(at.x,maxf(118.0,at.y-radius-14.0)),32,color,true)
	var support=model.level.get("presentation",{}).get("support",{})
	if not support.is_empty() and model.input_enabled:
		var entity=model.entities[support.entity]
		var remaining=maxf(0,(entity.next_activation-model.tick)/float(model.level.tick_hz))
		var at=model.center(entity)
		label(support.label+(" · 就绪" if remaining<=0 else " · %.1f 秒" % remaining),at+Vector2(-110,entity.height*.5+30),23,Color("#e1bd76"))
func draw_effects():
	var canvas = Vector2(model.level.layout.width,model.level.layout.height)
	for serial in model.active_effects:
		var instance=model.active_effects[serial];var definition=model.level.effects[instance.effect]
		var age=(model.tick-instance.start_tick)/float(model.level.tick_hz)
		var t=clampf(age*1000/definition.duration_ms,0,1)
		var at=Vector2(instance.position[0],instance.position[1]);var color=Color(definition.color);color.a*=1-t
		var radius=float(definition.get("radius",80))
		var anchor_uv = definition.get("anchor_uv",[])
		match definition.kind:
			"shot_trace":
				var muzzle = Vector2(canvas.x*.5,canvas.y-30)
				if not anchor_uv.is_empty():muzzle = canvas*Vector2(anchor_uv[0],anchor_uv[1])
				draw_shot_trace(at,muzzle,radius,color,t)
			"attack_release":
				var destination = Vector2(canvas.x*.5,canvas.y*.86)
				if not anchor_uv.is_empty():destination = canvas*Vector2(anchor_uv[0],anchor_uv[1])
				draw_attack_release(at,destination,radius,color,t)
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
				var source = instance.get("source",support.get("entity",""))
				if not source.is_empty():draw_line(model.center(model.entities[source]),at,color,2,true)
				draw_arc(at,35+60*t,0,TAU,32,color,3,true)
			"warning":draw_arc(at,radius*(1-.5*t),0,TAU,32,color,4,true)
			"player_hit":
				draw_player_hit(canvas,Color(definition.color),t,int(serial),definition.get("label",""))
		if definition.kind!="player_hit" and definition.has("label"):label(definition.label,at+Vector2(0,-20-t*40),26,color,true)

func draw_shot_trace(at: Vector2, muzzle: Vector2, radius: float, color: Color, age: float) -> void:
	var direction = (muzzle-at).normalized()
	var normal = direction.orthogonal()
	var tail = muzzle.lerp(at,age)
	draw_line(tail,at,color,maxf(1.0,18.0*(1.0-age)),true)
	draw_line(tail,at,Color(1.0,.98,.84,color.a),maxf(1.0,5.0*(1.0-age)),true)
	draw_circle(muzzle,35.0*(1.0-age),Color(color,color.a*.65))
	draw_circle(at,maxf(3.0,radius*.28*(1.0-age)),Color(1.0,.98,.84,color.a))
	draw_arc(at,radius*(.55+age),0,TAU,32,color,5,true)
	for offset in [direction,-direction,normal,-normal]:
		draw_line(at+offset*radius*.5,at+offset*radius*1.18,color,5,true)

func draw_attack_release(at: Vector2, destination: Vector2, radius: float, color: Color, age: float) -> void:
	var direction = (destination-at).normalized()
	var normal = direction.orthogonal()
	var tip = at.lerp(destination,minf(1.0,age*2.6))
	for offset in [-.65,0.0,.65]:
		var start = at + normal*radius*offset
		var end = tip + normal*radius*offset*.3
		draw_line(start,end,Color(.16,.025,.045,color.a),22,true)
		draw_line(start,end,color,9,true)
	draw_arc(at,radius*(.65+age),0,TAU,36,color,7,true)

func draw_player_hit(canvas: Vector2, color: Color, age: float, serial: int, caption: String) -> void:
	var strength = 1.0 - age
	draw_rect(Rect2(Vector2.ZERO,canvas),Color(color,.32*strength))
	for i in range(8):
		var inset = float(i)*9.0
		draw_rect(Rect2(Vector2.ONE*inset,canvas-Vector2.ONE*inset*2.0),Color(color,.88*strength*(1.0-i/9.0)),false,10)
	for i in range(16):
		var x = float((i*137+serial*43)%int(canvas.x))
		draw_circle(Vector2(x,canvas.y-(i%3)*19),float(28+(i%4)*13),Color(.24,.025,.05,.8*strength))
	var message_y = canvas.y*.77
	var message_alpha = minf(1.0,strength*2.6)
	draw_rect(Rect2(canvas.x*.5-225,message_y-58,450,78),Color(.17,.035,.05,.9*message_alpha))
	label(caption,Vector2(canvas.x*.5,message_y),46,Color(1.0,.86,.8,message_alpha),true)

func draw_hud():
	var presentation=model.level.get("presentation",{})
	var canvas=Vector2(model.level.layout.width,model.level.layout.height)
	var stats=model.section_stats();var section=stats.section
	draw_rect(Rect2(0,0,canvas.x,80),Color(.018,.025,.045,.8))
	label(presentation.get("title",""),Vector2(25,36),30)
	if not section.is_empty():
		if stats.section_total > 0:
			label("第 %d / %d %s · %s" % [section.index,stats.section_count,presentation.get("labels",{}).get("section_unit","段"),section.title],Vector2(25,67),25)
			label("本段 %d / %d · %s %d / %d" % [stats.section_cleared,stats.section_total,presentation.get("labels",{}).get("progress","完成"),stats.cleared,stats.total],Vector2(canvas.x*.47,48),27,Color("#dfbc77"),true)
		else:
			label(section.title,Vector2(25,67),25)
	var resources=[]
	for field in model.level.get("hud",[]):resources.append(field.label+" "+str(int(model.resources[field.resource])))
	# Right-align resource text without depending on game-specific counter names.
	var resource_text="  ".join(resources)
	var width=font.get_string_size(resource_text,HORIZONTAL_ALIGNMENT_LEFT,-1,26).x
	label(resource_text,Vector2(canvas.x-width-25,45),26)
	if not section.is_empty() and model.phase != "result":
		if stats.section_total == 0:
			draw_rect(Rect2(0,canvas.y-85,canvas.x,85),Color(.018,.025,.045,.82))
			label(section.get("hint",""),Vector2(canvas.x*.5,canvas.y-32),32,Color("#efd5a4"),true)
		else:
			label(section.get("hint",""),Vector2(canvas.x*.5,canvas.y-22),25,Color("#dbc8a8"),true)
	var context=model.presentation_context
	if context.mode=="player" and context.lifecycle=="ready":
		draw_rect(Rect2(Vector2.ZERO,canvas),Color(.015,.02,.04,.72))
		label(presentation.get("title",""),Vector2(canvas.x*.5,canvas.y*.34),68,Color("#ebd8b0"),true)
		label(presentation.get("subtitle",""),Vector2(canvas.x*.5,canvas.y*.43),34,Color("#cfa773"),true)
		label(presentation.get("instructions",""),Vector2(canvas.x*.5,canvas.y*.58),29,Color("#dfd0b4"),true)
		var controls = "Enter 或点击开始 · 鼠标 / 光枪射击"
		if model.available_commands().has("RELOAD"):controls += " · R 换弹"
		label(controls,Vector2(canvas.x*.5,canvas.y*.72),30,Color("#e3bd76"),true)
	elif model.phase=="result":
		draw_rect(Rect2(Vector2.ZERO,canvas),Color(.02,.025,.045,.65))
		label(presentation.get("labels",{}).get("result_success","完成") if model.result=="clear" else presentation.get("labels",{}).get("result_failure","失败"),Vector2(canvas.x*.5,canvas.y*.4),62,Color("#e7c994"),true)
		label("%s %d / %d · Enter 或点击重试" % [presentation.get("labels",{}).get("progress","完成"),stats.cleared,stats.total],Vector2(canvas.x*.5,canvas.y*.54),32,Color("#e0c59e"),true)
		if model.result == "clear" and not section.is_empty() and stats.section_total == 0:
			label(section.get("hint",""),Vector2(canvas.x*.5,canvas.y*.48),29,Color("#e0c59e"),true)
	elif context.mode=="player" and context.lifecycle=="paused":
		draw_rect(Rect2(Vector2.ZERO,canvas),Color(.02,.025,.045,.5))
		label("已暂停",Vector2(canvas.x*.5,canvas.y*.44),56,Color("#e7c994"),true)
		label("Enter / Esc 继续",Vector2(canvas.x*.5,canvas.y*.54),30,Color("#e0c59e"),true)
