extends SceneTree
## Native read-only review prototype; simulation and hit geometry share LevelRuntime.
const Loader = preload("res://core/level_loader.gd")
const Session = preload("res://core/level_session.gd")
const Codec = preload("res://core/pose_codec.gd")
const CuePlayer=preload("res://core/level_audio.gd")
const Timeline=preload("res://tools/review_timeline.gd")
class Preview:
	extends Control
	var model
	var owner_tool
	var shown = []
	var textures = {}
	var scale_factor = 1.0
	var origin = Vector2.ZERO
	var overlay = true
	var native_viewport
	func contour(item):
		var image=item.image
		var key="edge:"+str(image.get_instance_id())+":"+str(item.source)+":"+str(item.tint.a)
		if textures.has(key):return textures[key]
		var edge=Image.create(image.get_width(),image.get_height(),false,Image.FORMAT_RGBA8)
		edge.fill(Color.TRANSPARENT)
		for y in range(maxi(0,int(item.source.position.y)),mini(image.get_height(),int(ceil(item.source.end.y)))):
			for x in range(maxi(0,int(item.source.position.x)),mini(image.get_width(),int(ceil(item.source.end.x)))):
				if image.get_pixel(x,y).a*item.tint.a<.5:continue
				for offset in [Vector2i(-1,0),Vector2i(1,0),Vector2i(0,-1),Vector2i(0,1)]:
					var q=Vector2i(x,y)+offset
					if not item.source.has_point(Vector2(q)) or q.x<0 or q.y<0 or q.x>=image.get_width() or q.y>=image.get_height() or image.get_pixel(q.x,q.y).a*item.tint.a<.5:
						edge.set_pixel(x,y,Color.WHITE);break
		textures[key]=ImageTexture.create_from_image(edge)
		return textures[key]
	func _gui_input(event):
		if model==null or not event is InputEventMouseButton or not event.pressed or event.button_index!=MOUSE_BUTTON_LEFT:
			return
		var point = (event.position-origin)/scale_factor
		var canvas = Vector2(model.level.layout.width,model.level.layout.height)
		if Rect2(Vector2.ZERO,canvas).has_point(point):
			owner_tool.queue_shot(point,shown)
	func _draw():
		draw_rect(Rect2(Vector2.ZERO,size),Color("#111827"))
		if model == null:return
		var canvas = Vector2(model.level.layout.width,model.level.layout.height)
		scale_factor = minf(size.x/canvas.x,size.y/canvas.y)
		origin = (size-canvas*scale_factor)*.5
		shown = model.geometry()
		owner_tool.session.submit(shown)
		var base = Transform2D(0,origin).scaled_local(Vector2.ONE*scale_factor)
		if native_viewport!=null:
			draw_texture_rect(native_viewport.get_texture(),Rect2(origin,canvas*scale_factor),false)
		for item in shown:
			var key = item.image.get_instance_id()
			if not textures.has(key):textures[key]=ImageTexture.create_from_image(item.image)
			draw_set_transform_matrix(base*item.transform)
			var color = Color("#59b8aa")
			if item.kind=="protected":color=Color("#d9ad6b")
			if item.kind=="invalid":color=Color("#556071")
			if item.kind=="blocker":color=Color("#293141")
			if native_viewport==null:draw_texture_rect_region(textures[key],Rect2(Vector2.ZERO,item.size),item.source,color)
			if overlay and not item.kind.is_empty():draw_texture_rect_region(contour(item),Rect2(Vector2.ZERO,item.size),item.source,Color("#e2e8f0"))
		draw_set_transform_matrix(Transform2D.IDENTITY)
var model
var session=Session.new()
var clock
var preview
var info
var event_tree
var slider
var note
var status
var source_label
var running = false
var adjusting = false
var build_path = ""
var asset_root = ""
var review_dir = ""
var capture_path = ""
var quit_capture = false
var evidence_dir=""
var audio
var speed=1.0
var previous_build={}
var loaded_path=""
var previous_path=""
var smoke=false
var capture_tick=150
var recording_path=""
var timeline
var catalog_tree
var graph
var loop_enabled=false
var loop_a=0
var loop_b=0
var reload_button
var coin_button
func _initialize():
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--build="):build_path=arg.trim_prefix("--build=")
		if arg.begins_with("--assets="):asset_root=arg.trim_prefix("--assets=")
		if arg.begins_with("--reviews="):review_dir=arg.trim_prefix("--reviews=")
		if arg.begins_with("--capture="):capture_path=arg.trim_prefix("--capture=")
		if arg=="--quit-after-capture":quit_capture=true
		if arg.begins_with("--evidence="):evidence_dir=arg.trim_prefix("--evidence=")
		if arg=="--review-smoke":smoke=true
		if arg.begins_with("--capture-tick="):capture_tick=int(arg.trim_prefix("--capture-tick="))
		if arg.begins_with("--recording="):recording_path=arg.trim_prefix("--recording=" )
	call_deferred("open")
func button(parent,text,action):
	var node=Button.new();node.text=text;node.pressed.connect(action);parent.add_child(node);return node
func open():
	if build_path.is_empty() or asset_root.is_empty():
		push_error("Use start_level_review.ps1 or supply --build and --assets")
		quit(2);return
	root.title="GunForge — 关卡审阅（开发原型）"
	root.size=Vector2i(1440,900)
	var content=Control.new();content.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT);root.add_child(content)
	var font=SystemFont.new();font.font_names=PackedStringArray(["Microsoft YaHei","Noto Sans CJK SC"])
	content.add_theme_font_override("font",font)
	var margin=MarginContainer.new();margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side in ["margin_left","margin_right","margin_top","margin_bottom"]:margin.add_theme_constant_override(side,16)
	content.add_child(margin)
	var column=VBoxContainer.new();margin.add_child(column)
	source_label=Label.new();column.add_child(source_label)
	var toolbar=HBoxContainer.new();column.add_child(toolbar)
	button(toolbar,"从头播放",func():reset();running=true;refresh())
	button(toolbar,"播放 / 暂停",func():running=not running;refresh())
	button(toolbar,"前进一帧",func():running=false;advance_once();refresh())
	reload_button=button(toolbar,"换弹",func():queue_command("RELOAD"))
	coin_button=button(toolbar,"续关",func():queue_command("COIN"))
	button(toolbar,"Alpha 命中轮廓",func():preview.overlay=not preview.overlay;preview.queue_redraw())
	var speed_select=OptionButton.new()
	for text in ["0.5 倍速","1 倍速","2 倍速","4 倍速"]:speed_select.add_item(text)
	speed_select.select(1);speed_select.item_selected.connect(func(i):speed=[.5,1.0,2.0,4.0][i]);toolbar.add_child(speed_select)
	button(toolbar,"声音开关",func():audio.enabled=not audio.enabled;audio.sync(true))
	button(toolbar,"保存回放",save_recording)
	button(toolbar,"打开构建",choose_build)
	var versions_bar=HBoxContainer.new();column.add_child(versions_bar)
	button(versions_bar,"查看版本差异",show_diff)
	button(versions_bar,"切换上一版本",func():
		if not previous_path.is_empty():build_path=previous_path;load_build())
	button(versions_bar,"采用当前候选",confirm_adopt)
	button(versions_bar,"打开回放",choose_recording)
	button(versions_bar,"标记 A",func():loop_a=clock.tick)
	button(versions_bar,"标记 B",func():loop_b=clock.tick)
	button(versions_bar,"循环 A–B",func():loop_enabled=not loop_enabled)
	button(versions_bar,"最近输入判定",show_last_input)
	status=Label.new();column.add_child(status)
	var split=HSplitContainer.new();split.size_flags_vertical=Control.SIZE_EXPAND_FILL;column.add_child(split)
	var left=VBoxContainer.new();left.size_flags_horizontal=Control.SIZE_EXPAND_FILL;split.add_child(left)
	preview=Preview.new();preview.custom_minimum_size=Vector2(720,430);preview.size_flags_vertical=Control.SIZE_EXPAND_FILL;preview.owner_tool=self;left.add_child(preview)
	preview.clip_contents=true
	timeline=Timeline.new();timeline.owner_tool=self;timeline.custom_minimum_size=Vector2(720,102);left.add_child(timeline)
	timeline.font=font
	slider=HSlider.new();slider.step=1;slider.value_changed.connect(func(v):
		if not adjusting:jump(int(v)))
	left.add_child(slider)
	var right=VBoxContainer.new();right.custom_minimum_size=Vector2(400,0);split.add_child(right)
	var tabs=TabContainer.new();tabs.custom_minimum_size=Vector2(400,220);right.add_child(tabs)
	event_tree=Tree.new();event_tree.name="事件";event_tree.columns=2;event_tree.column_titles_visible=true;event_tree.set_column_title(0,"时间 / 条件");event_tree.set_column_title(1,"事件");event_tree.item_selected.connect(select_event);tabs.add_child(event_tree)
	catalog_tree=Tree.new();catalog_tree.name="关卡树";catalog_tree.item_selected.connect(select_catalog);tabs.add_child(catalog_tree)
	graph=GraphEdit.new();graph.name="依赖图";graph.minimap_enabled=false;tabs.add_child(graph)
	info=TextEdit.new();info.editable=false;info.size_flags_vertical=Control.SIZE_EXPAND_FILL;right.add_child(info)
	note=TextEdit.new();note.placeholder_text="批注：期望怎样调整？哪些内容必须保留？";note.custom_minimum_size=Vector2(400,110);right.add_child(note)
	button(right,"保存当前时间的批注",save_note)
	load_build()
	if not recording_path.is_empty():
		var file=FileAccess.open(recording_path,FileAccess.READ)
		var record=file.get_var(false) if file!=null else null
		if not record is Dictionary or record.get("build_id","")!=model.build.build_id:
			push_error("Recording build mismatch");quit(2);return
		session.load_recording(record)
	if smoke:
		await smoke_test();return
	if not capture_path.is_empty():
		if recording_path.is_empty():session.start()
		for i in range(capture_tick):session.step()
		refresh()
		await process_frame
		await RenderingServer.frame_post_draw
		var error=root.get_texture().get_image().save_png(capture_path)
		print(JSON.stringify({"capture":capture_path,"error":error}))
		if quit_capture:quit(0 if error==OK else 1)
func load_build():
	var compiled=JSON.parse_string(FileAccess.get_file_as_string(build_path))
	var next_model=Loader.open(compiled,asset_root)
	if next_model==null:
		if model==null:quit(2)
		else:status.text="构建校验失败；保留当前版本，请重新编译"
		return
	if model!=null:previous_build=model.build.duplicate(true);previous_path=loaded_path
	model=next_model;loaded_path=build_path;running=false
	preview.textures.clear()
	if preview.native_viewport!=null:preview.native_viewport.queue_free();preview.native_viewport=null
	if model.has_method("mount"):
		var native=SubViewport.new();native.size=Vector2i(model.level.layout.width,model.level.layout.height);native.disable_3d=true;native.render_target_update_mode=SubViewport.UPDATE_ALWAYS
		root.add_child(native);model.mount(native);preview.native_viewport=native
	session.setup(model);clock=session.clock
	if audio!=null:audio.queue_free()
	audio=CuePlayer.new();root.add_child(audio);audio.setup(model,asset_root)
	audio.enabled=model.level.get("presentation",{}).get("default_sound",false)
	preview.model=model
	timeline.model=model
	update_version_label()
	slider.max_value=session.max_tick
	event_tree.clear();var tree_root=event_tree.create_item();tree_root.set_text(0,"事件依赖");event_tree.hide_root=true
	for id in model.level.event_order:
		var item=event_tree.create_item(tree_root);item.set_text(0,("%.3f 秒" % (float(model.build.source_map[id].tick)/60.0)) if model.build.source_map[id].has("tick") else "条件触发");item.set_text(1,id);item.set_metadata(0,id)
	if model.has_method("review_events"):
		for entry in model.review_events():
			var item=event_tree.create_item(tree_root);item.set_text(0,entry.when);item.set_text(1,entry.id);item.set_metadata(0,entry)
	populate_catalog();populate_graph()
	info.text=JSON.stringify({"level":model.level.id,"build_id":model.build.build_id,"layout":model.level.layout,"controls":model.level.get("controls",{}),"events":model.level.events,"ruleset_data":model.level.get("ruleset_data",{})},"  ")
	refresh()
func reset():
	running=false;session.start();clock=session.clock;refresh()
	audio.clear()
func asset_map():
	return model.geometry_assets()
func queue_shot(point,pose):
	if not running:
		var hit=model.resolver.exact(point,pose)
		var id=hit.get("id","")
		info.text=JSON.stringify({"selected_entity":id,"geometry_hit":hit,"parameters":model.entities.get(id,{}),"queries":model.queries},"  ")
		return
	if model.phase!="running":return
	session.enqueue("SHOT",point)
func queue_command(event):
	session.enqueue(event)
	if not running:session.step();refresh()
func advance_once():
	session.step()
func _process(delta):
	if preview==null:return
	if audio!=null:
		for player in audio.players.values():player.stream_paused=not running
	if running and model.phase=="running":
		session.advance(delta*speed)
		if loop_enabled and loop_b>loop_a and clock.tick>=loop_b:session.seek(loop_a);audio.sync(true)
		refresh()
func refresh():
	if model.has_method("set_presentation_context"):model.set_presentation_context("review","playing" if running else "paused")
	reload_button.visible=model.available_commands().has("RELOAD");coin_button.visible=model.available_commands().has("COIN")
	var fields=[]
	for field in model.level.get("hud",[]):fields.append(field.label+" "+str(model.resources[field.resource]))
	var hud=" · ".join(fields) if not fields.is_empty() else JSON.stringify(model.resources)
	status.text="%s · %s  |  %.3f 秒 / %.3f 秒  |  %s  |  命中 %d / %d  |  %s" % ["播放" if running else "暂停",model.phase,clock.tick/60.0,session.max_tick/60.0,hud,model.hits,model.shots,model.result]
	adjusting=true;slider.max_value=session.max_tick;slider.value=clock.tick;adjusting=false
	preview.queue_redraw()
	timeline.queue_redraw()
	if audio!=null:audio.sync()
func jump(at):
	running=false;session.seek(at);audio.sync(true);refresh()
func select_event():
	var item=event_tree.get_selected()
	if item==null:return
	var id=item.get_metadata(0)
	if id is Dictionary:
		info.text=JSON.stringify(id,"  ");return
	info.text=JSON.stringify({"event_id":id,"design":model.level.events[id],"source":model.build.source_map[id],"fired":model.fired.get(id,0),"state":model.public_state()},"  ")
func save_note(author="user"):
	if review_dir.is_empty() or note.text.strip_edges().is_empty():return
	var text=note.text
	running=false
	DirAccess.make_dir_recursive_absolute(review_dir)
	var id="note-"+str(Time.get_unix_time_from_system()).replace(".","-")+"-"+str(Time.get_ticks_usec())
	var file=review_dir.path_join(id+".json")
	var selected=event_tree.get_selected()
	var entry={"comment_id":id,"source_revision":model.build.source_revision,"build_id":model.build.build_id,"tick":clock.tick,"time_ms":clock.tick*1000.0/60,"anchor":selected.get_metadata(0) if selected else null,"text":text,"status":"open","author":author,"state":model.public_state(),"submission_id":session.submission_id}
	var saved=await capture_evidence(id)
	if saved.is_empty():status.text="证据保存失败；批注未登记";return
	entry.evidence=saved
	FileAccess.open(file,FileAccess.WRITE).store_string(JSON.stringify(entry,"\t"))
	note.text="";status.text="批注已保存："+file
func evidence_root():
	if evidence_dir.is_empty():evidence_dir=asset_root.get_base_dir().path_join("gunforge_cache/level_design/review-evidence")
	DirAccess.make_dir_recursive_absolute(evidence_dir)
	return evidence_dir
func save_recording():
	var path=evidence_root().path_join("replay-"+str(Time.get_unix_time_from_system()).replace(".","-")+".bin")
	var file=FileAccess.open(path,FileAccess.WRITE)
	if file==null:status.text="无法保存回放";return
	file.store_var(session.recording());file.close();status.text="已保存回放："+path
func capture_evidence(id):
	var directory=evidence_root().path_join(id)
	if DirAccess.make_dir_recursive_absolute(directory)!=OK:return {}
	var previous=preview.overlay
	var files={}
	for mode in ["player","alpha"]:
		preview.overlay=mode=="alpha";preview.queue_redraw()
		await process_frame;await RenderingServer.frame_post_draw
		var path=directory.path_join(mode+".png")
		var box=Rect2i(preview.global_position+preview.origin,Vector2(model.level.layout.width,model.level.layout.height)*preview.scale_factor)
		if root.get_texture().get_image().get_region(box).save_png(path)!=OK:preview.overlay=previous;return {}
		files[mode]={"path":path,"sha256":FileAccess.get_sha256(path)}
	preview.overlay=previous;preview.queue_redraw()
	var record=directory.path_join("input.bin");var file=FileAccess.open(record,FileAccess.WRITE)
	if file==null:return {}
	file.store_var(session.recording());file.close()
	files.recording={"path":record,"sha256":FileAccess.get_sha256(record)}
	return files
func choose_build():
	running=false
	var dialog=FileDialog.new();dialog.access=FileDialog.ACCESS_FILESYSTEM;dialog.file_mode=FileDialog.FILE_MODE_OPEN_FILE;dialog.filters=PackedStringArray(["*.json ; 编译后的关卡 JSON"]);dialog.size=Vector2i(900,600)
	root.add_child(dialog);dialog.file_selected.connect(func(path):build_path=path;load_build();dialog.queue_free());dialog.canceled.connect(dialog.queue_free);dialog.popup_centered()
func adopted_pointer():
	var path=asset_root.path_join("gunforge/level_design/adopted/"+model.level.id+".json")
	return JSON.parse_string(FileAccess.get_file_as_string(path)) if FileAccess.file_exists(path) else {}
func update_version_label():
	var adopted=adopted_pointer()
	var label="已采用构建" if adopted.get("build_id","")==model.build.build_id else "候选预览，未采用"
	source_label.text=model.level.id+"  |  构建 "+model.build.build_id.substr(0,12)+"  |  源 "+model.build.source_revision.substr(0,12)+"  |  seed "+str(model.level.seed)+"  |  "+label
func diff_values(a,b,path=""):
	var out=[]
	if a is Dictionary and b is Dictionary:
		var keys=a.keys()
		for key in b:
			if not keys.has(key):keys.append(key)
		keys.sort()
		for key in keys:
			var at=path+"/"+str(key)
			if not a.has(key):out.append({"path":at,"added":b[key]})
			elif not b.has(key):out.append({"path":at,"removed":a[key]})
			else:out.append_array(diff_values(a[key],b[key],at))
	elif var_to_str(a)!=var_to_str(b):out.append({"path":path,"before":a,"after":b})
	return out
func show_diff():
	if previous_build.is_empty():info.text="请先打开另一个构建；这里将按稳定 ID 显示两个版本的字段差异。";return
	info.text=JSON.stringify({"base_build":previous_build.build_id,"new_build":model.build.build_id,"changes":diff_values(previous_build.level,model.level)},"  ")
func confirm_adopt():
	running=false
	var current=adopted_pointer()
	var output=[]
	var source=asset_root.path_join("gunforge/level_design/packages/"+model.level.id+"/revisions/"+model.build.source_revision+"/level.json")
	var result=OS.execute(asset_root.path_join(".venv/Scripts/python.exe"),PackedStringArray([asset_root.path_join("gunforge/pipeline/level_design/checks.py"),source]),output,true)
	var report=JSON.parse_string("\n".join(output))
	if result!=0 or not report is Dictionary:
		status.text="无法采用：源版本或检查报告不完整";return null
	var dialog=ConfirmationDialog.new();dialog.title="采用已预览的关卡版本";dialog.dialog_text="";dialog.dialog_hide_on_ok=false
	var column=VBoxContainer.new();column.custom_minimum_size=Vector2(710,0);dialog.add_child(column)
	column.add_theme_font_override("font",info.get_theme_font("font"))
	var label=Label.new();label.text="关卡："+model.level.id+"\n源："+model.build.source_revision+"\n构建："+model.build.build_id+"\n采用会切换本地指针并保留回退记录。";column.add_child(label)
	var reason=LineEdit.new();reason.placeholder_text="采用理由（必填）";column.add_child(reason);dialog.register_text_enter(reason)
	var boxes=[]
	var titles={"HUD_UNDECLARED":"未声明通用 HUD；当前可能由原画面渲染器提供", "DISPLAY_PROFILE_UNTESTED":"此画布比例还需要真实光枪和显示设备验证", "HUMAN_DIFFICULTY_UNCALIBRATED":"功能机器人尚不能代表真人难度", "LEGACY_RULE_POLICY":"点灯奖励、续灯和续关计分保留旧版策略"}
	for warning in report.warnings:
		var box=CheckBox.new();box.text="已核对："+titles.get(warning.code,warning.message);box.set_meta("code",warning.code);column.add_child(box);boxes.append(box)
	root.add_child(dialog);dialog.confirmed.connect(func():
		if reason.text.strip_edges().is_empty():status.text="未采用：请填写理由";return
		for box in boxes:
			if not box.button_pressed:status.text="未采用：请核对仍开放的警告";return
		var response=[]
		var arguments=PackedStringArray([asset_root.path_join("gunforge/pipeline/level_design/versions.py"),"adopt",model.level.id,model.build.source_revision,"--expected",current.get("source_revision","none"),"--reason",reason.text,"--actor","user","--build-id",model.build.build_id])
		for box in boxes:arguments.append("--ack-warning");arguments.append(box.get_meta("code"))
		var adopted=OS.execute(asset_root.path_join(".venv/Scripts/python.exe"),arguments,response,true)
		status.text="采用完成；旧版可通过版本指针记录回退" if adopted==0 else "采用失败："+"\n".join(response)
		update_version_label();dialog.queue_free())
	dialog.canceled.connect(dialog.queue_free);dialog.popup_centered(Vector2i(760,360))
	return dialog
func smoke_test():
	running=false
	for i in range(150):session.step()
	refresh();await process_frame;await RenderingServer.frame_post_draw
	var before=model.public_state()
	jump(20);jump(150)
	var exact=var_to_bytes(before)==var_to_bytes(model.public_state())
	# Letterbox pixels can show off-canvas debug contours but cannot accept shots.
	await process_frame;await RenderingServer.frame_post_draw
	var outside = InputEventMouseButton.new()
	outside.button_index = MOUSE_BUTTON_LEFT
	outside.pressed = true
	outside.position = preview.origin - Vector2(0,1)
	running = true
	preview._gui_input(outside)
	running = false
	var outside_ignored = session.queue.pending.is_empty()
	note.text="Automated UI/evidence probe; not a user annotation or acceptance."
	await save_note("test_harness")
	var saved=note.text.is_empty()
	save_recording()
	var before_pointer=adopted_pointer()
	var confirmation=confirm_adopt()
	var dialog_ok=confirmation!=null
	if confirmation!=null:
		await process_frame;await RenderingServer.frame_post_draw
		dialog_ok=confirmation.get_texture().get_image().save_png(evidence_root().path_join("adoption-dialog.png"))==OK
		confirmation.queue_free()
	dialog_ok=dialog_ok and before_pointer==adopted_pointer()
	var output={"passed":exact and saved and dialog_ok and outside_ignored,"seek_exact":exact,"evidence_saved":saved,"off_canvas_input_ignored":outside_ignored,"adoption_dialog_without_adoption":dialog_ok,"build_id":model.build.build_id,"author":"test_harness"}
	print(JSON.stringify(output));quit(0 if output.passed else 1)
func populate_catalog():
	catalog_tree.clear();var top=catalog_tree.create_item();top.set_text(0,model.level.id);catalog_tree.hide_root=false
	for section in ["entities","queries","cues","resources","ruleset_data","controls","effects","sections","presentation"]:
		var branch=catalog_tree.create_item(top);branch.set_text(0,section);branch.collapsed=true
		for id in model.level.get(section,{}):
			var item=catalog_tree.create_item(branch);item.set_text(0,str(id));item.set_metadata(0,{"section":section,"id":id,"pointer":"/"+section+"/"+str(id)})
func select_catalog():
	var item=catalog_tree.get_selected();var entry=item.get_metadata(0)
	if not entry is Dictionary:return
	info.text=JSON.stringify({"source":entry.pointer,"design":model.level[entry.section][entry.id],"runtime":model.queries.get(entry.id,model.entities.get(entry.id,{}))},"  ")
func populate_graph():
	for child in graph.get_children():
		if child is GraphNode:graph.remove_child(child);child.queue_free()
	graph.clear_connections()
	var nodes={};var index=0
	for id in model.level.event_order:
		var node=GraphNode.new();node.name="event_"+str(index);node.title=id;node.draggable=false;node.position_offset=Vector2((index%3)*260,int(index/3)*115)
		var label=Label.new();label.text=JSON.stringify(model.level.events[id].trigger);label.custom_minimum_size=Vector2(210,30);node.add_child(label)
		node.set_slot(0,true,0,Color("#59b8aa"),true,0,Color("#d9ad6b"));graph.add_child(node);nodes[id]=node.name;index+=1
	for id in model.level.event_order:
		var trigger=model.level.events[id].trigger
		if trigger.has("after") and nodes.has(trigger.after):graph.connect_node(nodes[trigger.after],0,nodes[id],0)
func choose_recording():
	running=false
	var dialog=FileDialog.new();dialog.access=FileDialog.ACCESS_FILESYSTEM;dialog.file_mode=FileDialog.FILE_MODE_OPEN_FILE;dialog.filters=PackedStringArray(["*.bin ; 同构建输入回放"]);root.add_child(dialog)
	dialog.file_selected.connect(func(path):
		var file=FileAccess.open(path,FileAccess.READ)
		var record=file.get_var(false) if file!=null else null
		if not record is Dictionary or record.get("build_id","")!=model.build.build_id:status.text="回放版本不匹配；未载入"
		else:session.load_recording(record);audio.clear();refresh();status.text="已载入回放："+path
		dialog.queue_free())
	dialog.canceled.connect(dialog.queue_free);dialog.popup_centered(Vector2i(900,600))
func show_last_input():
	if session.tape.is_empty():info.text="当前路径尚无已消费输入。";return
	var entry=session.tape[-1].duplicate(true)
	if entry.input.has("geometry"):entry.input.geometry=entry.input.geometry.map(func(item):return {"asset":item.asset,"id":item.id,"kind":item.kind,"source":item.source,"transform":item.transform,"size":item.size,"alpha_multiplier":item.tint.a})
	info.text=JSON.stringify(entry,"  ")
