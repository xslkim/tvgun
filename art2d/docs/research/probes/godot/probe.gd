extends SceneTree

func _initialize() -> void:
	call_deferred("_probe")

func _probe() -> void:
	var args = OS.get_cmdline_user_args()
	if args.size() != 1:
		push_error("Pass the absolute path to demos/poc/world.json after --")
		quit(2)
		return
	var data = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	if data == null:
		push_error("Unable to load shared POC JSON")
		quit(2)
		return
	var rig = data.rig
	var clip = data.clip
	var scene = Node2D.new()
	root.add_child(scene)
	var skeleton = Skeleton2D.new()
	skeleton.name = "Skeleton"
	scene.add_child(skeleton)
	var nodes = {}
	for b in rig.bones:
		var bone = Bone2D.new()
		bone.name = b.id
		bone.set_autocalculate_length_and_angle(false)
		bone.position = Vector2(b.x, -b.y)
		bone.rotation_degrees = -b.a
		bone.rest = bone.transform
		if b.has("parent"):
			nodes[b.parent].add_child(bone)
		else:
			skeleton.add_child(bone)
		nodes[b.id] = bone

	var player = AnimationPlayer.new()
	scene.add_child(player)
	var animation = Animation.new()
	animation.length = clip.duration
	animation.loop_mode = Animation.LOOP_LINEAR
	for b in rig.bones:
		var track = animation.add_track(Animation.TYPE_VALUE)
		var property_path = str(scene.get_path_to(nodes[b.id])) + ":rotation"
		animation.track_set_path(track, NodePath(property_path))
		for i in range(clip.frames.size()):
			var delta = clip.frames[i].get(b.id, [0, 0, 0])
			var time = float(i) * clip.duration / (clip.frames.size() - 1)
			animation.track_insert_key(track, time, deg_to_rad(-(b.a + delta[2])))
	var lib = AnimationLibrary.new()
	lib.add_animation("idle", animation)
	player.add_animation_library("", lib)
	player.play("idle")
	player.advance(0)
	var max_distance = 0.0
	var max_angle = 0.0
	for i in range(data.frames.size()):
		player.seek(i / 30.0, true)
		var expected = data.frames[i]
		for id in nodes:
			var bone = nodes[id]
			var w = expected[id]
			max_distance = max(max_distance, bone.global_position.distance_to(Vector2(w.x, -w.y)))
			max_angle = max(max_angle, abs(wrapf(-bone.global_rotation_degrees - w.a, -180, 180)))
	print("Godot ", Engine.get_version_info().string, " | ", nodes.size(), " Bone2D, ", data.frames.size(),
		" samples, position error ", max_distance, " px, angle error ", max_angle, " deg")
	quit(0 if max_distance < 0.01 and max_angle < 0.01 else 1)
