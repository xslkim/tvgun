extends RefCounted
const Item = preload("raster_item.gd")

static func encode(items: Array, assets: Dictionary) -> Array:
	var out = []
	for item in items:
		var key = ""
		for candidate in assets:
			if assets[candidate].image == item.image:
				key = candidate
				break
		assert(not key.is_empty(), "Pose references an unregistered image")
		out.append({"asset":key,"source":item.source,"transform":item.transform,
			"size":item.size,"id":item.id,"kind":item.kind,"tint":item.tint,"generation":item.generation})
	return out

static func decode(data: Array, assets: Dictionary) -> Array:
	var out = []
	for entry in data:
		assert(assets.has(entry.asset), "Snapshot requires missing asset")
		var item = Item.new()
		item.image = assets[entry.asset].image
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
