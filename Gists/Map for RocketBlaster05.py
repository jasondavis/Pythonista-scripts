
'''
NOTE: This requires the latest beta of Pythonista 1.6 (build 160022)
Demo of a custom ui.View subclass that embeds a native map view using MapKit (via objc_util). Tap and hold the map to drop a pin.
The MapView class is designed to be reusable, but it doesn't implement *everything* you might need. I hope that the existing methods give you a basic idea of how to add new capabilities though. For reference, here's Apple's documentation about the underlying MKMapView class: http://developer.apple.com/library/ios/documentation/MapKit/reference/MKMapView_Class/index.html
If you make any changes to the OMMapViewDelegate class, you need to restart the app. Because this requires creating a new Objective-C class, the code can basically only run once per session (it's not safe to delete an Objective-C class at runtime as long as instances of the class potentially exist).
'''

from objc_util import *
import ast
import ctypes
import ui
import location
import os
import time
import weakref

MKPointAnnotation = ObjCClass('MKPointAnnotation')
MKPinAnnotationView = ObjCClass('MKPinAnnotationView')
MKAnnotationView = ObjCClass('MKAnnotationView')			# for photo as pin
UIColor = ObjCClass('UIColor') # used to set pin color

def mapView_annotationView_calloutAccessoryControlTapped_(self,cmd,mk_mapview, mk_annotationView,mk_calloutAccessoryControlTapped):
	global locs
	pinView = ObjCInstance(mk_annotationView)
	mapView = ObjCInstance(mk_mapview)
	annotation = pinView.annotation()
	title = str(annotation.title())
	lat = annotation.coordinate().a
	lon = annotation.coordinate().b
	mapView.ui_view.add_pin(lat, lon, 'deleted user point', str((lat, lon)))
	# if user location, append a line in file with (lat,lon)
	if title == 'Current Location':
		# change lat,lon to differentiate user pin of trash pin
		lat += 0.00000001
		lon += 0.00000001
		c = (lat,lon)
		locs.append(c)
		mapView.deselectAnnotation_animated_(annotation, True)
	else:
		# delete old pin only if not the current location pin
		mapView.removeAnnotation_(annotation)
	# append a line in file with (lat,lon,'trash')
	c = (lat,lon,'trash')
	locs.append(c)
	with open(path,mode='wt') as f:
		content = str(locs)
		f.write(content)
		
def mapView_viewForAnnotation_(self,cmd,mk_mapview,mk_annotation):
	global own_ui_image, del_ui_image
	try:
		# not specially called in the same sequence as pins created
		# should have one MK(Pin)AnnotationView by type (ex: pin color)
		annotation = ObjCInstance(mk_annotation)
		mapView = ObjCInstance(mk_mapview)
		if annotation.isKindOfClass_(MKPointAnnotation):
			tit = str(annotation.title())
			subtit = str(annotation.subtitle())
			id = tit
			pinView = mapView.dequeueReusableAnnotationViewWithIdentifier_(id)			
			if not pinView:
				if tit == 'Current Location':
					# Show a photo instead of a pin: use MKAnnotationView	
					pinView = MKAnnotationView.alloc().initWithAnnotation_reuseIdentifier_(annotation,id)						
					pinView.setImage_(own_ui_image.objc_instance)			
				elif tit == 'deleted user point':
					# Show a photo instead of a pin: use MKAnnotationView	
					pinView = MKAnnotationView.alloc().initWithAnnotation_reuseIdentifier_(annotation,id)						
					pinView.setImage_(del_ui_image.objc_instance)		
				else:
					# Modify pin color: use MKPinAnnotationView
					pinView = MKPinAnnotationView.alloc().initWithAnnotation_reuseIdentifier_(annotation,id)
					pinView.animatesDrop   = True   # Animated pin falls like a drop
					if tit == 'Dropped Pin':
						pinView.pinColor = 0 # 0=red 1=green 2=purple
					elif tit == 'Current Location':
						pinView.pinColor = 2 # 0=red 1=green 2=purple
					else:
						pinView.pinColor = 1 # 0=red 1=green 2=purple
				pinView.canShowCallout = True  	# tap-> show title	

				if tit in ['user point', 'Current Location']:
					# RightCalloutAccessoryView for trash button		
					bo = ObjCClass('UIButton').alloc().init()
					bo.setTitle_forState_('🗑',0)
					bo.setFrame_(CGRect(CGPoint(0,0), CGSize(40,40)))				
					pinView.setRightCalloutAccessoryView_(bo)			
			
			else:
				pinView.annotation = annotation
			return pinView.ptr
		return None
	except Exception as e:
		print('Error on line {}'.format(sys.exc_info()[-1].tb_lineno), type(e).__name__, e)
		
# Build method of MKMapView Delegate
methods = [mapView_annotationView_calloutAccessoryControlTapped_, mapView_viewForAnnotation_]
protocols = ['MKMapViewDelegate']
try:
	MyMapViewDelegate = ObjCClass('MyMapViewDelegate')
except Exception as e:
	MyMapViewDelegate = create_objc_class('MyMapViewDelegate', methods=methods, protocols=protocols)	

# _map_delegate_cache is used to get a reference to the MapView from the (Objective-C) delegate callback. The keys are memory addresses of `OMMapViewDelegate` (Obj-C) objects, the values are `ObjCInstance` (Python) objects. This mapping is necessary because `ObjCInstance` doesn't guarantee that you get the same object every time when you instantiate it with a pointer (this may change in future betas). MapView stores a weak reference to itself in the specific `ObjCInstance` that it creates for its delegate.
_map_delegate_cache = weakref.WeakValueDictionary()

class CLLocationCoordinate2D (Structure):
	_fields_ = [('latitude', c_double), ('longitude', c_double)]
class MKCoordinateSpan (Structure):
	_fields_ = [('d_lat', c_double), ('d_lon', c_double)]
class MKCoordinateRegion (Structure):
	_fields_ = [('center', CLLocationCoordinate2D), ('span', MKCoordinateSpan)]

class MapView (ui.View):
	@on_main_thread
	def __init__(self, *args, **kwargs):
		ui.View.__init__(self, *args, **kwargs)
		MKMapView = ObjCClass('MKMapView')


		frame = CGRect(CGPoint(0, 0), CGSize(self.width, self.height))
		self.mk_map_view = MKMapView.alloc().initWithFrame_(frame)
		self.mk_map_view.ui_view = self
		#print(dir(self.mk_map_view.region()))
		flex_width, flex_height = (1<<1), (1<<4)
		self.mk_map_view.setAutoresizingMask_(flex_width|flex_height)
		self_objc = ObjCInstance(self)
		self_objc.addSubview_(self.mk_map_view)
		self.mk_map_view.release()
		self.long_press_action = None
		self.scroll_action = None
		#NOTE: The button is only used as a convenient action target for the gesture recognizer. While this isn't documented, the underlying UIButton object has an `-invokeAction:` method that takes care of calling the associated Python action.
		self.gesture_recognizer_target = ui.Button()
		self.gesture_recognizer_target.action = self.long_press
		UILongPressGestureRecognizer = ObjCClass('UILongPressGestureRecognizer')
		self.recognizer = UILongPressGestureRecognizer.alloc().initWithTarget_action_(self.gesture_recognizer_target, sel('invokeAction:')).autorelease()
		self.mk_map_view.addGestureRecognizer_(self.recognizer)
		self.long_press_location = ui.Point(0, 0)
		self.map_delegate = MyMapViewDelegate.alloc().init()#.autorelease()
		self.mk_map_view.setDelegate_(self.map_delegate)
		self.map_delegate.map_view_ref = weakref.ref(self)
		_map_delegate_cache[self.map_delegate.ptr] = self.map_delegate
		
		# Add a map type button
		maptype_button = ui.Button()
		maptype_button.frame = (self.width-82,2,80,20)
		maptype_button.border_width = 1
		maptype_button.corner_radius = 5
		maptype_button.border_color = 'red'
		maptype_button.background_color = (1,0,0,0.8)
		maptype_button.tint_color = 'black'
		maptype_button.title = 'map type'
		maptype_button.action = self.maptype_button_action
		self.add_subview(maptype_button)
		self.mk_map_view.mapType = 0
		
		camera_button = ui.Button()
		camera_button.frame = (maptype_button.x-40-2,2,40,20)
		camera_button.border_width = 1
		camera_button.corner_radius = 5
		camera_button.border_color = 'red'
		camera_button.background_color = (1,0,0,0.8)
		self.add_subview(camera_button)
		camera_button.tint_color = 'black'
		camera_button.title = '3D'
		camera_button.action = self.camera_button_action
		
		self.update_interval = 2	# call update each 2 seconds
		
	def update(self):
		location.start_updates()
		time.sleep(0.1)
		loc = location.get_location()
		location.stop_updates()
		if loc:
			lat, lon = loc['latitude'], loc['longitude']
			# update face pin location
			coord = CLLocationCoordinate2D(lat, lon)
			self.user_annotation.setCoordinate_(coord, restype=None,  argtypes=[CLLocationCoordinate2D])
		
	def maptype_button_action(self,sender):
		x = self.x + sender.x + sender.width/2
		y = 70 + self.y + sender.y + sender.height
		sub_menu_dict = {'standard':0, 'satellite':1, 'hybrid':2, 'satelliteFlyover':3, 'hybridFlyover':4, 'mutedStandard':5}
		sub_menu = []
		for k in [*sub_menu_dict]:
			sub_menu.append(k)
		tv = ui.TableView()
		tv.frame = (0,0,180,280)
		tv.data_source = ui.ListDataSource(items=sub_menu)
		tv.allows_multiple_selection = False
		tv.selected_row = (0,self.mk_map_view.mapType())
		tv.delegate = self
		tv.present('popover',popover_location=(x,y),hide_title_bar=True)
		tv.wait_modal()
		map_type = tv.selected_row[1]
		#print(map_type)
		if map_type != self.mk_map_view.mapType():
			self.mk_map_view.mapType = map_type
	
	def camera_button_action(self,sender):
		# tests have shown that mkmapview has a default mkcamera
		if sender.title == '3D':
			self.mk_map_view.camera().setPitch_(45)
			self.mk_map_view.camera().setAltitude_(500)
			self.mk_map_view.camera().setHeading_(45)
			self.mk_map_view.setShowsBuildings_(True)
			sender.title = '2D'
		else:
			self.mk_map_view.camera().setPitch_(0)
			sender.title = '3D'
			
	def tableview_did_select(self, tableview, section, row):
		tableview.close()
	
	def long_press(self, sender):
		#NOTE: The `sender` argument will always be the dummy ui.Button that's used as the gesture recognizer's target, just ignore it...
		gesture_state = self.recognizer.state()
		if gesture_state == 1 and callable(self.long_press_action):
			loc = self.recognizer.locationInView_(self.mk_map_view)
			self.long_press_location = ui.Point(loc.x, loc.y)
			self.long_press_action(self)
	
	@on_main_thread
	def add_pin(self, lat, lon, title, subtitle=None, select=False):
		'''Add a pin annotation to the map'''
		MKPointAnnotation = ObjCClass('MKPointAnnotation')
		coord = CLLocationCoordinate2D(lat, lon)
		annotation = MKPointAnnotation.alloc().init().autorelease()
		annotation.setTitle_(title)
		if subtitle:
			annotation.setSubtitle_(subtitle)
		annotation.setCoordinate_(coord, restype=None, argtypes=[CLLocationCoordinate2D])
		self.mk_map_view.addAnnotation_(annotation)
		if select:
			self.mk_map_view.selectAnnotation_animated_(annotation, True)
		return annotation
	
	@on_main_thread
	def remove_all_pins(self):
		'''Remove all annotations (pins) from the map'''
		self.mk_map_view.removeAnnotations_(self.mk_map_view.annotations())
		
	@on_main_thread
	def set_region(self, lat, lon, d_lat, d_lon, animated=False):
		'''Set latitude/longitude of the view's center and the zoom level (specified implicitly as a latitude/longitude delta)'''
		region = MKCoordinateRegion(CLLocationCoordinate2D(lat, lon), MKCoordinateSpan(d_lat, d_lon))
		self.mk_map_view.setRegion_animated_(region, animated, restype=None, argtypes=[MKCoordinateRegion, c_bool])
	
	@on_main_thread
	def set_center_coordinate(self, lat, lon, animated=False):
		'''Set latitude/longitude without changing the zoom level'''
		coordinate = CLLocationCoordinate2D(lat, lon)
		self.mk_map_view.setCenterCoordinate_animated_(coordinate, animated, restype=None, argtypes=[CLLocationCoordinate2D, c_bool])
	
	@on_main_thread
	def get_center_coordinate(self):
		'''Return the current center coordinate as a (latitude, longitude) tuple'''
		coordinate = self.mk_map_view.centerCoordinate(restype=CLLocationCoordinate2D, argtypes=[])
		return coordinate.latitude, coordinate.longitude
	
	@on_main_thread
	def point_to_coordinate(self, point):
		'''Convert from a point in the view (e.g. touch location) to a latitude/longitude'''
		coordinate = self.mk_map_view.convertPoint_toCoordinateFromView_(CGPoint(*point), self._objc_ptr, restype=CLLocationCoordinate2D, argtypes=[CGPoint, c_void_p])
		return coordinate.latitude, coordinate.longitude
	
	def _notify_region_changed(self):
		if callable(self.scroll_action):
			self.scroll_action(self)


# --------------------------------------
# DEMO:

def long_press_action(sender):
	global locs,path
	# Add a pin when the MapView recognizes a long-press
	c = sender.point_to_coordinate(sender.long_press_location)
	# this of only to special process asked in forum
	# https://forum.omz-software.com/topic/7077/removing-custom-pins-with-map-api
	for annotation in sender.mk_map_view.annotations():
		if str(annotation.title()) == 'Dropped Pin':
			lat = annotation.coordinate().a
			lon = annotation.coordinate().b
			sender.mk_map_view.removeAnnotation_(annotation)
			sender.add_pin(lat, lon, 'user point', str((lat, lon)))
			break
	sender.add_pin(c[0], c[1], 'Dropped Pin', str(c), select=True)
	sender.set_center_coordinate(c[0], c[1], animated=True)
	locs.append(c)
	with open(path,mode='wt') as f:
		content = str(locs)
		f.write(content)

def scroll_action(sender):
	# Show the current center coordinate in the title bar after the map is scrolled/zoomed:
	sender.name = 'lat/long: %.2f, %.2f' % sender.get_center_coordinate()
	
def compute_region_param(l):
	# Compute min and max of latitude and longitude
	min_lat = min(l,key = lambda x:x[0])[0]
	max_lat = max(l,key = lambda x:x[0])[0]
	min_lon = min(l,key = lambda x:x[1])[1]
	max_lon = max(l,key = lambda x:x[1])[1]
	d_lat = 1.2*(max_lat-min_lat)
	d_lon = 1.2*(max_lon-min_lon)
	return min_lat,min_lon,max_lat,max_lon,d_lat,d_lon

def build_pin(path):
	my_ui_image = ui.Image.named(path)	
	dx,dy = 28,86
	v = ui.View(frame=(0,0,dx,dx),corner_radius=dx/2)
	iv = ui.ImageView(frame=(0,0,dx,dx))
	iv.image = my_ui_image
	v.add_subview(iv)
	with ui.ImageContext(dx,dx) as ctx:					
		v.draw_snapshot()						# if circular cropped
		my_ui_image = ctx.get_image()
	# image with pin and its foot, coloured circle replaced by the photo)
	with ui.ImageContext(dx,dy) as ctx:	
		foot = ui.Path.oval(dx/2-2,dy/2-1,4,2)
		ui.set_color((0,0,0,1))
		foot.fill()
		pin = ui.Path.rounded_rect(dx/2-1,dx/2,2,dy/2-dx/2,1)
		ui.set_color((0.6,0.6,0.6,1))
		pin.fill()
		my_ui_image.draw(0,0,dx,dx)
		my_ui_image = ctx.get_image()	
	# circular image without foot not pin			
	#d = 28
	#v = ui.View(frame=(0,0,d,d),corner_radius=d/2)
	#iv = ui.ImageView(frame=(0,0,d,d))
	#v.add_subview(iv)
	#iv.image = my_ui_image
	#with ui.ImageContext(d,d) as ctx:					
	#	v.draw_snapshot()						# if circular cropped
	#	my_ui_image = ctx.get_image()
	return my_ui_image

def main():
	global locs, path
	
	global own_ui_image,del_ui_image										
	own_ui_image = build_pin('emj:Man')
	del_ui_image = build_pin('iob:ios7_trash_outline_32')

	# create main view
	mv = ui.View()
	mv.name = 'Map for RocketBlaster05'
	mv.background_color = 'white'
	mv.present('fullscreen')
	w,h = ui.get_screen_size()
	# Create and present a MapView:
	v = MapView(frame=(0,0,w,h-76))
	mv.add_subview(v)
	v.long_press_action = long_press_action
	v.scroll_action = scroll_action
	path = 'a.loc'
	trashs = {}
	locs = []
	if os.path.exists(path):
		with open(path,mode='rt') as f:
			aux = {}
			content = f.read()
			pts = ast.literal_eval(content)
			for pt in pts:
				if len(pt) == 2:
					lat,lon = pt
					aux[(lat,lon)] = True
				else:
					lat,lon,t = pt
					aux[(lat,lon)] = False
				locs.append(pt)
			for pt in aux.keys():
				lat,lon = pt
				if aux[pt]:
					v.add_pin(lat, lon, 'user point', str((lat, lon)))
				else:
					v.add_pin(lat, lon, 'deleted user point', str((lat, lon)))
	# center on user location				
	import location
	location.start_updates()
	time.sleep(0.1)
	loc = location.get_location()
	location.stop_updates()
	if loc:
		lat, lon = loc['latitude'], loc['longitude']
		# add a purple pin for user's location
		v.user_annotation = v.add_pin(lat, lon, 'Current Location', str((lat, lon)))
		if 1==0:#locs:
			l = locs + [(lat,lon)]	# include user location but not in locs
			min_lat,min_lon,max_lat,max_lon,d_lat,d_lon = compute_region_param(l)
			v.set_region((min_lat+max_lat)/2, (min_lon+max_lon)/2,1.2*(max_lat-min_lat), 1.2*(max_lon-min_lon), animated=True)	
		else:
			v.set_region(lat, lon, 0.05, 0.05, animated=True)

if __name__ == '__main__':
	main()
