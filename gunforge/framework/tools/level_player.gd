extends SceneTree
## Shared player shell. Device coordinates and UI never access game-specific fields.
const Loader=preload("res://core/level_loader.gd")
const Session=preload("res://core/level_session.gd")
const Review=preload("res://tools/level_review.gd")
const Frame=preload("res://core/screen_frame.gd")
const Gun=preload("res://core/gun_input.gd")
const Http=preload("res://core/http_controls.gd")
const Audio=preload("res://core/level_audio.gd")
const Calibration=preload("res://core/calibration.gd")
const Metrics=preload("res://core/visible_metrics.gd")
const Codec=preload("res://core/pose_codec.gd")

class DesktopInput extends Node:
	var handle_key: Callable

	func _input(event: InputEvent) -> void:
		if event is InputEventKey and event.pressed and not event.echo:
			if handle_key.call(event.keycode):
				get_viewport().set_input_as_handled()

var session=Session.new()
var frame=Frame.new()
var gun=Gun.new()
var http=Http.new()
var model
var preview
var status
var audio
var border
var dark
var network=false
var build_path=""
var assets=""
var quit_after=0.0
var elapsed=0.0
var completions={}
var calibration=Calibration.new()
var isolated_settings=false
func _initialize():
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--build="):build_path=arg.trim_prefix("--build=")
		if arg.begins_with("--assets="):assets=arg.trim_prefix("--assets=")
		if arg.begins_with("--quit-after="):quit_after=float(arg.trim_prefix("--quit-after="))
		if arg=="--network":network=true
		if arg=="--isolated-settings":isolated_settings=true
	call_deferred("open")
func open():
	model=Loader.open(JSON.parse_string(FileAccess.get_file_as_string(build_path)),assets)
	if model==null:quit(2);return
	root.title="GunForge — "+model.level.id;root.size=Vector2i(1280,720)
	border=ColorRect.new();border.color=Color.WHITE;root.add_child(border)
	dark=ColorRect.new();dark.color=Color.BLACK;root.add_child(dark)
	preview=Review.Preview.new();preview.owner_tool=self;preview.model=model;preview.overlay=false;preview.clip_contents=true;root.add_child(preview)
	var desktop_input = DesktopInput.new()
	desktop_input.handle_key = handle_key
	root.add_child(desktop_input)
	if model.has_method("mount"):
		var viewport=SubViewport.new();viewport.size=Vector2i(model.level.layout.width,model.level.layout.height);viewport.disable_3d=true;root.add_child(viewport);model.mount(viewport);preview.native_viewport=viewport
	session.real_time_inputs=true
	session.setup(model)
	session.set_pause("ready",true)
	var settings=ConfigFile.new()
	if not isolated_settings and settings.load("user://settings.cfg")==OK:
		frame.configure(settings.get_value("display","profile","monitor"))
		for key in ["white","dark","outer"]:frame.set(key,settings.get_value(frame.profile,key,frame.get(key)))
		calibration.matrix=settings.get_value(frame.profile,"calibration",calibration.matrix)
	session.input_consumed.connect(finish_input)
	status=Label.new();status.mouse_filter=Control.MOUSE_FILTER_IGNORE;root.add_child(status)
	status.visible=model.level.get("presentation",{}).get("debug_shell",true)
	var font=SystemFont.new();font.font_names=PackedStringArray(["Microsoft YaHei"]);status.add_theme_font_override("font",font)
	audio=Audio.new();root.add_child(audio);audio.setup(model,assets);audio.enabled=true
	gun.open();http.open(8080,handle_http)
	root.size_changed.connect(layout);layout()
	print(JSON.stringify({"level_player_ready":true,"build_id":model.build.build_id,"udp_errors":gun.bind_errors,"http_error":http.bind_error}))
func layout():
	var box=frame.screen_rect(root.size);border.position=box.position;border.size=box.size
	var inset=frame.white*box.size.x/1920.0;dark.position=box.position+Vector2.ONE*inset;dark.size=box.size-Vector2.ONE*inset*2
	box=frame.content_rect(root.size);preview.position=box.position;preview.size=box.size;status.position=box.position+Vector2(8,8)
func queue_shot(point,_pose):
	if network or not in_playfield(point):return
	if session.pause_reasons.has("ready") or model.phase=="result":
		enqueue_device({"event":"START"})
		return
	session.enqueue("SHOT",point)

func in_playfield(point: Vector2) -> bool:
	return Rect2(Vector2.ZERO,Vector2(model.level.layout.width,model.level.layout.height)).has_point(point)
func from_norm(point):return (frame.norm_to_window(calibration.apply(point),root.size)-preview.position-preview.origin)/preview.scale_factor
func enqueue_device(event):
	var command=event.event
	if command=="AIM":return
	if command=="LOST":
		for entry in session.queue.pending:
			if entry.event.event=="SHOT":finish_input(entry.order,{"ok":false,"reason":"tracking_lost"})
		session.queue.pending=session.queue.pending.filter(func(entry):return entry.event.event!="SHOT");return
	if command=="EXIT":session.set_pause("manual",not session.pause_reasons.has("manual"));return
	if command=="START":
		if model.phase=="result":
			for order in completions.keys():finish_input(order,{"ok":false,"reason":"session_restarted"})
			session.start();audio.clear()
		session.set_pause("ready",false)
		session.set_pause("manual",false);return
	if command=="SHOT":
		var point=from_norm(event.aim)
		if in_playfield(point):session.enqueue("SHOT",point)
		elif model.available_commands().has("RELOAD"):session.enqueue("RELOAD")
	else:session.enqueue(command)
func _process(delta):
	if model==null:return
	elapsed+=delta
	var events=gun.poll(elapsed,frame.white,frame.dark)
	session.set_pause("tracking",network and not gun.valid)
	if network:
		for event in events:enqueue_device(event)
	http.poll()
	session.advance(delta)
	for order in completions.keys():
		if elapsed-completions[order].at>5:completions.erase(order)
	if session.closed:gun.close();http.close();quit();return
	if model.has_method("set_presentation_context"):model.set_presentation_context("player",session.public_state().lifecycle)
	audio.sync()
	for player in audio.players.values():player.stream_paused=not session.pause_reasons.is_empty()
	var reload_hint = "　R 换弹" if model.available_commands().has("RELOAD") else ""
	status.text="%s  %s  %s\nEnter 开始 / 重试 / 恢复%s　Esc 暂停　G 光枪模式　Q 退出" % [session.public_state().lifecycle,JSON.stringify(model.resources),str(session.pause_reasons.keys()),reload_hint]
	preview.queue_redraw()
	if quit_after>0 and elapsed>=quit_after:gun.close();http.close();quit()
func handle_key(keycode: Key) -> bool:
	match keycode:
		KEY_ENTER, KEY_KP_ENTER:enqueue_device({"event":"START"})
		KEY_ESCAPE:enqueue_device({"event":"EXIT"})
		KEY_R:
			if not model.available_commands().has("RELOAD"):return false
			session.enqueue("RELOAD")
		KEY_G:network=not network
		KEY_Q:gun.close();http.close();quit()
		_:return false
	return true
func handle_http(command,payload,completion):
	if command=="STATE":
		var targets=[]
		var pose=Codec.decode(session.submission,model.geometry_assets())
		var visible=Metrics.sample(pose,model.resolver,Vector2(model.level.layout.width,model.level.layout.height),8)
		for id in visible.targets:
			var point=visible.targets[id].aim
			if point!=null:targets.append({"id":id,"point":[point.x,point.y]})
		return {"ok":true,"phase":model.phase,"lifecycle":session.public_state().lifecycle,"resources":model.resources.duplicate(true),"score":model.resources.get("score",0),"build_id":model.build.build_id,"shots":model.shots,"hits":model.hits,"visible_targets":targets}
	if command in ["START","EXIT"]:enqueue_device({"event":command});return {"ok":true}
	var point=from_norm(Vector2(payload.get("x",0),payload.get("y",0)))
	if command=="SHOT":
		if not point.is_finite():return {"ok":false,"reason":"invalid_coordinates"}
		if not in_playfield(point):
			if not model.available_commands().has("RELOAD"):return {"ok":false,"reason":"outside_playfield"}
			command="RELOAD"
	var order=session.queue.next_order
	if not session.enqueue(command,point):return {"ok":false,"reason":"paused_or_no_submission"}
	completions[order]={"callback":completion,"at":elapsed}
	return {"deferred":true}
func finish_input(order,result):
	if not completions.has(order):return
	var response=result.duplicate(true);response.score=model.resources.get("score",0)
	completions[order].callback.call(response);completions.erase(order)
