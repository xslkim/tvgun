extends RefCounted

var image: Image
var texture: Texture2D
var source = Rect2()
var transform = Transform2D.IDENTITY
var size = Vector2.ZERO
var id = ""
var kind = ""
var tint = Color.WHITE

func sample(point: Vector2) -> Color:
	var p = transform.affine_inverse() * point
	if not Rect2(Vector2.ZERO, size).has_point(p):
		return Color.TRANSPARENT
	var uv = p / size
	var xy = source.position + uv * source.size
	var x = clampi(int(xy.x), 0, image.get_width()-1)
	var y = clampi(int(xy.y), 0, image.get_height()-1)
	return image.get_pixel(x, y) * tint

func bounds() -> Rect2:
	return transform * Rect2(Vector2.ZERO, size)
