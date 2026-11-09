extends Control
## Inspection projection of the current 2D pose and authored motion.
signal entity_selected(id: String, center: Vector2, pose_scale: float)

enum Mode { SIDE, TOP }

var mode = Mode.SIDE
var model
var label_font: Font
var markers: Array[Dictionary] = []

func project(center: Vector2, pose_scale: float, canvas: Vector2, plot: Rect2) -> Vector2:
	var near = clampf(0.5 + log(maxf(pose_scale, 0.01)) / log(2.0) * 0.26, 0.06, 0.94)
	var screen = (center / canvas).clamp(Vector2.ZERO, Vector2.ONE)
	var coordinates = Vector2(screen.x, near) if mode == Mode.TOP else Vector2(1.0 - near, screen.y)
	return plot.position + coordinates * plot.size

func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), Color("#111827"))
	markers.clear()
	if model == null or label_font == null:
		return
	var canvas = Vector2(model.level.layout.width, model.level.layout.height)
	var plot = Rect2(54, 72, size.x - 108, size.y - 140)
	var top = mode == Mode.TOP
	var title = "俯视 · 屏幕横向 × 估算近远" if top else "侧视 · 估算近远 × 屏幕高度"
	draw_string(label_font, Vector2(22, 28), title, HORIZONTAL_ALIGNMENT_LEFT, -1, 20, Color("#dbeafe"))
	draw_string(label_font, Vector2(22, 52), "近远按缩放估算，未记录缩放的对象放在参考面。线条表示配置的运动路径。", HORIZONTAL_ALIGNMENT_LEFT, -1, 14, Color("#a5b4c6"))
	draw_rect(plot, Color("#172033"))
	for i in range(5):
		var step = float(i) / 4.0
		var x = plot.position.x + plot.size.x * step
		var y = plot.position.y + plot.size.y * step
		draw_line(Vector2(x, plot.position.y), Vector2(x, plot.end.y), Color("#334155"))
		draw_line(Vector2(plot.position.x, y), Vector2(plot.end.x, y), Color("#334155"))
	if top:
		draw_string(label_font, plot.position + Vector2(5, 18), "远处", HORIZONTAL_ALIGNMENT_LEFT, -1, 14)
		draw_string(label_font, plot.end + Vector2(-122, 23), "屏幕右侧", HORIZONTAL_ALIGNMENT_LEFT, -1, 14)
		draw_string(label_font, Vector2(plot.get_center().x - 24, plot.end.y + 23), "玩家侧", HORIZONTAL_ALIGNMENT_LEFT, -1, 14)
	else:
		draw_string(label_font, plot.position + Vector2(5, 18), "屏幕上方", HORIZONTAL_ALIGNMENT_LEFT, -1, 14)
		draw_string(label_font, Vector2(plot.position.x, plot.end.y + 23), "玩家侧", HORIZONTAL_ALIGNMENT_LEFT, -1, 14)
		draw_string(label_font, plot.end + Vector2(-40, 23), "远处", HORIZONTAL_ALIGNMENT_LEFT, -1, 14)

	var targets = {}
	for item in model.geometry():
		if item.id.is_empty() or item.kind in ["", "blocker", "decoration"]:
			continue
		var bounds: Rect2 = item.bounds()
		if targets.has(item.id):
			targets[item.id].bounds = targets[item.id].bounds.merge(bounds)
		else:
			targets[item.id] = {"bounds": bounds, "kind": item.kind}
	for id in targets:
		var entity: Dictionary = model.entities.get(id, {})
		var pose_scale: float = entity.get("pose_scale", 1.0)
		var center: Vector2 = targets[id].bounds.get_center()
		var point = project(center, pose_scale, canvas, plot)
		var color = Color("#77e2d2")
		if targets[id].kind == "protected":
			color = Color("#e5b972")
		elif entity.get("template") == "projectile":
			color = Color("#ff9468")
		var frames: Array = entity.get("motion_override", entity.get("motion", {})).get("frames", [])
		if frames.size() >= 2:
			var path = PackedVector2Array()
			var half_size = Vector2(entity.width, entity.height) * 0.5
			for frame in frames:
				path.append(project(Vector2(frame.x, frame.y) + half_size, frame.get("scale", 1.0), canvas, plot))
			draw_polyline(path, Color(color, 0.48), 2.0, true)
		markers.append({"id": id, "point": point, "center": center, "scale": pose_scale, "color": color})
	for marker in markers:
		draw_circle(marker.point, 6.0, marker.color)
		var label_at: Vector2 = marker.point + Vector2(9, -8)
		var label = str(marker.id)
		label_at.x = minf(label_at.x, size.x - label_font.get_string_size(label, HORIZONTAL_ALIGNMENT_LEFT, -1, 13).x - 8)
		draw_string_outline(label_font, label_at, label, HORIZONTAL_ALIGNMENT_LEFT, -1, 13, 4, Color("#111827"))
		draw_string(label_font, label_at, label, HORIZONTAL_ALIGNMENT_LEFT, -1, 13, marker.color)

func _gui_input(event: InputEvent) -> void:
	if not event is InputEventMouseButton or not event.pressed or event.button_index != MOUSE_BUTTON_LEFT:
		return
	var nearest = {}
	var best = 16.0
	for marker in markers:
		var distance: float = marker.point.distance_to(event.position)
		if distance < best:
			best = distance
			nearest = marker
	if not nearest.is_empty():
		entity_selected.emit(nearest.id, nearest.center, nearest.scale)
	accept_event()
