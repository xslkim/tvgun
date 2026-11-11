extends RefCounted
const Item = preload("raster_item.gd")

static func asset_id(image: Image, assets: Dictionary) -> String:
	for candidate in assets:
		if assets[candidate].image == image:
			return candidate
	assert(false, "Pose references an unregistered image")
	return ""

static func encode(items: Array, assets: Dictionary) -> Array:
	var out = []
	for item in items:
		var entry := {"asset":asset_id(item.image, assets),"source":item.source,"transform":item.transform,
			"size":item.size,"id":item.id,"kind":item.kind,"tint":item.tint,"generation":item.generation}
		if item.hit_image != null:
			entry.hit_asset = asset_id(item.hit_image, assets)
		out.append(entry)
	return out

static func decode(data: Array, assets: Dictionary) -> Array:
	var out = []
	for entry in data:
		assert(assets.has(entry.asset), "Snapshot requires missing asset")
		var item = Item.new()
		item.image = assets[entry.asset].image
		if entry.has("hit_asset"):
			item.hit_image = assets[entry.hit_asset].image
		item.texture = assets[entry.asset].texture
		item.source = entry.source
		item.transform = entry.transform
		item.size = entry.size
		item.id = entry.id
		item.kind = entry.kind
		item.tint = entry.tint
		item.generation=int(entry.get("generation",0))
		out.append(item)
	return out
