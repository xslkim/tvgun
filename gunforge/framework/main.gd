extends Node

const Frame = preload("core/screen_frame.gd")
const InputLink = preload("core/gun_input.gd")
const Hit = preload("core/hit_resolver.gd")
const Cal = preload("core/calibration.gd")
const Audio = preload("core/audio.gd")
const HttpControls = preload("core/http_controls.gd")
var frame = Frame.new()
var link = InputLink.new()
var http_controls = HttpControls.new()
var resolver = Hit.new()
var calibration = Cal.new()
var model
var scene
var viewport: SubViewport
var surface: TextureRect
var outer: ColorRect
var border: ColorRect
var dark: ColorRect
var network_mode = false
var cursor_norm = Vector2(960,540)
var sound
var debug_server = TCPServer.new()
var debug_clients = []
var debug_buffers = {}
var fixed = false
var elapsed = 0.0
var last_events = 0
var show_settings = false
var calibration_points = []
var calibration_from = []
var calibration_checks = []
var calibrating = false
var calibration_stage = 0
var raw_mouse = Vector2.ZERO
var calibration_before = []
var startup = {}
var stats = []
var max_stats = 600
var frame_sample = 0

func _ready():
	if not FileAccess.file_exists("res://runtime/level.json"):
		push_error("Run start_game.ps1 to build runtime assets first.")
		get_tree().quit(1)
		return
	model = load("res://runtime/game_rules.gd").new()
	model.setup(JSON.parse_string(FileAccess.get_file_as_string("res://runtime/level.json")))
	var game_script = load("res://runtime/game_scene.gd")
	scene = game_script.new()
	scene.model = model
	viewport = SubViewport.new()
	viewport.size = Vector2i(1776,936)
	viewport.disable_3d = true
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	add_child(viewport)
	viewport.add_child(scene)
	outer = ColorRect.new()
	outer.color = Color.BLACK
	outer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(outer)
	border = ColorRect.new()
	border.color = Color.WHITE
	border.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(border)
	dark = ColorRect.new()
	dark.color = Color.BLACK
	dark.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(dark)
	surface = TextureRect.new()
	surface.texture = viewport.get_texture()
	surface.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	surface.stretch_mode = TextureRect.STRETCH_SCALE
	surface.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var material = ShaderMaterial.new()
	material.shader = load("res://shaders/limit.gdshader")
	surface.material = material
	add_child(surface)
	sound = Audio.new()
	add_child(sound)
	load_settings()
	var args = OS.get_cmdline_user_args()
	fixed = "--fixed" in args
	if "--gun" in args:
		network_mode = true
	if "--autostart" in args:
		model.reset()
	var game_port = 9000
	var disco_port = 8001
	for arg in args:
		if arg.begins_with("--port="):
			game_port = int(arg.trim_prefix("--port="))
		if arg.begins_with("--discovery="):
			disco_port = int(arg.trim_prefix("--discovery="))
	link.open(game_port,disco_port)
	http_controls.open(game_port,http_command)
	var debug_error = debug_server.listen(19010,"127.0.0.1")
	startup = {"godot":Engine.get_version_info().string,"renderer":RenderingServer.get_current_rendering_method(),
			   "adapter":RenderingServer.get_video_adapter_name(),
			   "network_errors":link.bind_errors,"http_error":http_controls.bind_error,"debug_error":debug_error}
	get_tree().root.size_changed.connect(layout)
	layout()
	scene.update_frame()
	print(JSON.stringify({"GunForge_ready":true,"startup":startup}))

func layout():
	var window = get_viewport().get_visible_rect().size
	outer.size = window
	var rect = frame.screen_rect(window)
	border.position = rect.position
	border.size = rect.size
	var inset = frame.white*rect.size.x/1920
	dark.position = rect.position+Vector2.ONE*inset
	dark.size = rect.size-Vector2.ONE*inset*2
	rect = frame.content_rect(window)
	surface.position = rect.position
	surface.size = rect.size

func save_settings():
	var config = ConfigFile.new()
	config.load("user://settings.cfg")
	config.set_value("display","profile",frame.profile)
	for key in ["white","dark","outer"]:
		config.set_value(frame.profile,key,frame.get(key))
	config.set_value(frame.profile,"calibration",calibration.matrix)
	config.save("user://settings.cfg")

func load_settings():
	var config = ConfigFile.new()
	config.load("user://settings.cfg")
	frame.configure(config.get_value("display","profile","monitor"))
	for key in ["white","dark","outer"]:
		frame.set(key,config.get_value(frame.profile,key,frame.get(key)))
	calibration.matrix = config.get_value(frame.profile,"calibration",calibration.matrix)

func set_profile(name: String):
	save_settings()
	frame.configure(name)
	var cfg = ConfigFile.new()
	cfg.load("user://settings.cfg")
	for key in ["white","dark","outer"]:
		frame.set(key,cfg.get_value(name,key,frame.get(key)))
	calibration.matrix = cfg.get_value(name,"calibration",[1.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0])
	layout()
	link.last_frame_sent = -100
	save_settings()

func to_content(point: Vector2) -> Vector2:
	var corrected = calibration.apply(point)
	return (corrected-Vector2.ONE*(frame.white+frame.dark)) / frame.content_size() * Vector2(1776,936)

func offscreen(point: Vector2) -> bool:
	return not Rect2(Vector2.ZERO,Vector2(1920,1080)).has_point(calibration.apply(point))

func locked() -> bool:
	return not network_mode or link.valid

func _process(delta):
	elapsed = Time.get_ticks_msec()/1000.0
	for event in link.poll(elapsed,frame.white,frame.dark):
		if network_mode:
			dispatch(event)
	http_controls.poll()
	if not fixed:
		advance(minf(delta,.1))
	poll_debug()
	if scene:
		scene.cursor = to_content(cursor_norm)
		scene.locked = locked()
		scene.network_mode = network_mode
		scene.profile = frame.profile
		scene.extras = settings_text() if show_settings else ""
		scene.update_frame()
	frame_sample += 1
	if frame_sample%30==0:
		stats.append({"fps":Engine.get_frames_per_second(),"process_ms":Performance.get_monitor(Performance.TIME_PROCESS)*1000,
					  "frame_ms":delta*1000,
					  "texture_bytes":RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TEXTURE_MEM_USED),
					  "draw_calls":RenderingServer.get_rendering_info(RenderingServer.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME)})
		if stats.size()>max_stats:
			stats.pop_front()

func advance(dt: float):
	model.tick(dt,locked())
	scene.view_clock = model.total
	while last_events<model.events.size():
		sound.cue(model.events[last_events].event)
		last_events += 1

func dispatch(event: Dictionary):
	var command = event.event
	if command=="AIM":
		cursor_norm = event.aim
	elif command=="SHOT":
		var aim = event.get("aim",cursor_norm)
		if calibrating:
			calibrate_shot(aim)
			return
		var point = to_content(aim)
		var hit = resolver.resolve(point,scene.hit_items) if Rect2(Vector2.ZERO,Vector2(1776,936)).has_point(point) else {}
		if model.command("SHOT",hit,offscreen(aim),locked()):
			scene.flash_time = model.total
			scene.flash_point = point
			scene.last_kind = hit.get("kind","miss")
			sound.cue("shot")
	elif command=="EXIT":
		model.user_paused = not model.user_paused
	else:
		model.command(command)
	scene.update_frame()

func http_command(command: String, payload: Dictionary) -> Dictionary:
	if command=="STATE":
		return {"ok":true,"score":model.score,"phase":model.phase}
	var before = model.hits
	var event = {"event":command}
	if command=="SHOT":
		var point = Vector2(float(payload.x),float(payload.y))
		if not is_finite(point.x) or not is_finite(point.y) or point.length()>100000:
			return {"ok":false}
		event.aim = point
		cursor_norm = point
	dispatch(event)
	return {"ok":true,"score":model.score,"hit":model.hits>before}

func _unhandled_input(event):
	if event is InputEventMouseMotion and not network_mode:
		raw_mouse = frame.window_to_norm(event.position,get_viewport().get_visible_rect().size)
		cursor_norm = raw_mouse
	if event is InputEventMouseButton and event.pressed:
		if event.button_index==MOUSE_BUTTON_RIGHT:
			dispatch({"event":"RELOAD"})
		elif event.button_index==MOUSE_BUTTON_LEFT and not network_mode:
			var aim = frame.window_to_norm(event.position,get_viewport().get_visible_rect().size)
			dispatch({"event":"SHOT","aim":aim})
	if event is InputEventKey and event.pressed and not event.echo:
		match event.keycode:
			KEY_ENTER: dispatch({"event":"START"})
			KEY_5: dispatch({"event":"COIN"})
			KEY_R: dispatch({"event":"RELOAD"})
			KEY_ESCAPE:
				if calibrating:
					finish_calibration(false)
				elif show_settings:
					show_settings = false
				else:
					dispatch({"event":"EXIT"})
			KEY_F11:
				var mode = DisplayServer.window_get_mode()
				DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_WINDOWED if mode==DisplayServer.WINDOW_MODE_FULLSCREEN else DisplayServer.WINDOW_MODE_FULLSCREEN)
			KEY_G:
				network_mode = not network_mode
			KEY_F1:
				scene.debug = not scene.debug
			KEY_F2:
				show_settings = not show_settings
				model.user_paused = show_settings
			KEY_F3:
				set_profile("tv" if frame.profile=="monitor" else "monitor")
			KEY_C:
				begin_calibration()
			KEY_BRACKETLEFT, KEY_BRACKETRIGHT:
				if show_settings:
					frame.white = clampf(frame.white+(-2 if event.keycode==KEY_BRACKETLEFT else 2),12,40)
					layout()
					link.last_frame_sent = -100
					save_settings()
			KEY_MINUS, KEY_EQUAL:
				if show_settings:
					frame.dark = clampf(frame.dark+(-4 if event.keycode==KEY_MINUS else 4),24,72)
					layout()
					link.last_frame_sent = -100
					save_settings()

func settings_text() -> String:
	return "显示设置 · %s\nF3 切换显示器 / 电视配置\n[ / ] 白边 %d    - / = 暗区 %d\nC 进行 5 点校准与 4 点检查\nG 切换鼠标 / 光枪输入    F1 调试图层\nF11 全屏    Esc 返回" % [frame.profile,frame.white,frame.dark]

func begin_calibration():
	model.user_paused = true
	calibrating = true
	calibration_stage = 0
	calibration_before = calibration.matrix.duplicate()
	calibration_from = []
	calibration_checks = []
	calibration_points = [Vector2(960,540),Vector2(240,200),Vector2(1680,200),Vector2(1680,880),Vector2(240,880),
						  Vector2(600,360),Vector2(1320,360),Vector2(1320,720),Vector2(600,720)]
	update_calibration_ui()

func update_calibration_ui():
	var target = calibration_points[calibration_stage]
	scene.calibration_ui = {"target":(target-Vector2.ONE*(frame.white+frame.dark))/frame.content_size()*Vector2(1776,936),
							"text":"射击圆心 · %s %d / %d" % ["校准" if calibration_stage<5 else "独立检查",
								calibration_stage+1 if calibration_stage<5 else calibration_stage-4,5 if calibration_stage<5 else 4]}

func calibrate_shot(raw: Vector2):
	if calibration_stage<5:
		calibration_from.append(raw)
	else:
		calibration_checks.append(calibration.apply(raw).distance_to(calibration_points[calibration_stage]))
	calibration_stage += 1
	if calibration_stage==5:
		var prior = calibration.matrix.duplicate()
		if not calibration.fit(calibration_from,calibration_points.slice(0,5)):
			calibration.matrix = prior
			finish_calibration(false)
			return
	if calibration_stage==9:
		var passed = calibration_checks.max()<10
		finish_calibration(passed)
	else:
		update_calibration_ui()

func finish_calibration(passed: bool):
	calibrating = false
	scene.calibration_ui = {}
	model.user_paused = show_settings
	if passed:
		save_settings()
	else:
		calibration.matrix = calibration_before
	model.notify("calibration","校准通过" if passed else "校准取消或检查未通过，请重新校准")

func poll_debug():
	if debug_server.is_connection_available():
		var peer = debug_server.take_connection()
		debug_clients.append(peer)
		debug_buffers[peer.get_instance_id()] = ""
	for peer in debug_clients.duplicate():
		peer.poll()
		if peer.get_status()!=StreamPeerTCP.STATUS_CONNECTED:
			debug_clients.erase(peer)
			debug_buffers.erase(peer.get_instance_id())
			continue
		if peer.get_available_bytes()<=0:
			continue
		var id = peer.get_instance_id()
		debug_buffers[id] += peer.get_utf8_string(peer.get_available_bytes())
		if debug_buffers[id].length()>65536:
			peer.disconnect_from_host()
			continue
		while debug_buffers[id].contains("\n"):
			var cut = debug_buffers[id].find("\n")
			var line = debug_buffers[id].substr(0,cut)
			debug_buffers[id] = debug_buffers[id].substr(cut+1)
			var request = JSON.parse_string(line)
			var result = {"error":"Invalid JSON"}
			if request is Dictionary:
				result = debug_command(request)
			peer.put_data((JSON.stringify(result)+"\n").to_utf8_buffer())

func debug_command(request: Dictionary) -> Dictionary:
	match request.get("op",""):
		"state":
			var points = {}
			for id in scene.aim_points:
				var p = scene.aim_points[id]
				points[id] = [p.x,p.y]
			return {"state":model.snapshot(),"targets":points,"startup":startup,"performance":stats,"fixed":fixed,"gun":network_mode}
		"freeze":
			fixed = request.get("value",true)
		"step":
			if not fixed:
				return {"error":"Freeze the game clock before stepping"}
			for i in range(clampi(request.get("frames",1),1,600)):
				advance(1.0/60)
			scene.update_frame()
		"input":
			var event = {"event":request.get("event","")}
			if request.has("x") and request.has("y"):
				event.aim = Vector2(request.x,request.y)
				cursor_norm = event.aim
			dispatch(event)
		"mode":
			network_mode = request.get("gun",false)
		"profile":
			set_profile(request.get("name","monitor"))
		"capture":
			var path = request.get("path","")
			if not path.is_absolute_path() or not path.ends_with(".png"):
				return {"error":"Absolute PNG path required"}
			capture.call_deferred(path)
			return {"capture_scheduled":path}
		"quit":
			get_tree().quit()
		_:
			return {"error":"Unknown operation"}
	return {"state":model.snapshot()}

func capture(path: String):
	await RenderingServer.frame_post_draw
	var image = get_viewport().get_texture().get_image()
	var error = image.save_png(path)
	print(JSON.stringify({"capture":path,"error":error}))

func _exit_tree():
	link.close()
	http_controls.close()
	debug_server.stop()
