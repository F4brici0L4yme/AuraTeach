import bpy, math, sys
from mathutils import Vector

bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)

def mat(name, color, metallic=0.0, rough=.35):
    m=bpy.data.materials.new(name); m.diffuse_color=(*color,1); m.use_nodes=True
    p=m.node_tree.nodes.get('Principled BSDF'); p.inputs['Base Color'].default_value=(*color,1); p.inputs['Metallic'].default_value=metallic; p.inputs['Roughness'].default_value=rough
    return m
blue=mat('Azul tinta · carcasa',(.035,.20,.62),.28,.24); dark=mat('Goma negra · agarre',(.035,.045,.055),0,.62)
steel=mat('Acero · punta y clip',(.62,.69,.74),.82,.22); ink=mat('Cartucho de tinta',(.08,.22,.72),.12,.3)
white=mat('Plástico del pulsador',(.12,.3,.78),.18,.28); springmat=mat('Acero del resorte',(.72,.76,.8),.9,.18)

def cyl(name,x0,x1,r,material,r2=None,verts=48):
    r2=r if r2 is None else r2
    mid=(x0+x1)/2
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r, radius2=r2, depth=x1-x0, location=(mid,0,0), rotation=(0,math.pi/2,0))
    o=bpy.context.object; o.name=name; o.data.materials.append(material
    ); bevel=o.modifiers.new('Bordes suaves','BEVEL'); bevel.width=.35; bevel.segments=3
    o.modifiers.new('Normales','WEIGHTED_NORMAL'); return o

def spring(name,x0,x1,r,wire,material,turns=9):
    c=bpy.data.curves.new(name,'CURVE'); c.dimensions='3D'; c.bevel_depth=wire; c.bevel_resolution=3; c.resolution_u=16
    s=c.splines.new('POLY'); n=turns*32+1; s.points.add(n-1)
    for i,p in enumerate(s.points):
        t=i/(n-1); a=t*turns*2*math.pi; p.co=((x0+(x1-x0)*t),r*math.cos(a),r*math.sin(a),1)
    o=bpy.data.objects.new(name,c); bpy.context.collection.objects.link(o); c.materials.append(material); return o

# Component groups are left as separate, named meshes so a GLB viewer can select them.
cyl('Punta cónica de escritura',-116,-101,1.0,steel,5.5)
cyl('Cono frontal',-103,-88,6.0,blue,8.0)
cyl('Agarre estriado',-89,-62,8.0,dark)
for i in range(20):
    a=i*2*math.pi/20
    # fine raised grip ribs follow the rubber sleeve
    bpy.ops.mesh.primitive_cylinder_add(vertices=8,radius=.22,depth=24,location=(-75,7.85*math.cos(a),7.85*math.sin(a)),rotation=(0,math.pi/2,0))
    bpy.context.object.name=f'Estría de goma {i+1:02d}'; bpy.context.object.data.materials.append(dark)
cyl('Barril principal',-62,52,8.4,blue)
cyl('Banda frontal',-63,-61,8.8,steel)
cyl('Banda trasera',51,53,8.8,steel)
cyl('Cartucho de tinta',-99,75,1.65,ink)
cyl('Depósito de tinta',-56,42,1.9,ink)
cyl('Punta del cartucho',-102,-98,2.7,steel,1.65)
spring('Resorte de retorno',-57,-43,4.5,.52,springmat,8)
cyl('Guía del resorte',-44,-39,2.6,white)
cyl('Émbolo del pulsador',47,68,3.0,white,4.5)
cyl('Tapa trasera',66,79,7.5,white,6.0)
cyl('Corona pulsable',79,85,6.2,blue,6.2)

# Clip: a flattened, polished strip with a curved return, split into named pieces.
def bar(name,a,b,w,d,material,locz=6.4):
    mid=((a[0]+b[0])/2,(a[1]+b[1])/2); length=math.dist((a[0],a[1]),(b[0],b[1])); ang=math.atan2(b[1]-a[1],b[0]-a[0])
    bpy.ops.mesh.primitive_cube_add(size=1,location=(mid[0],mid[1],locz)); o=bpy.context.object; o.name=name
    o.dimensions=(length,w,d); o.rotation_euler[2]=ang; bpy.ops.object.transform_apply(location=False,rotation=False,scale=True); o.data.materials.append(material)
    be=o.modifiers.new('Clip redondeado','BEVEL'); be.width=.65; be.segments=4; o.modifiers.new('Normales','WEIGHTED_NORMAL')
bar('Anclaje del clip',(42,0),(50,0),5,2,steel,7)
bar('Clip · tramo recto',(48,0),(65,0),2.7,1.6,steel,10)
bar('Clip · curva',(65,0),(76,-2),2.7,1.6,steel,9)
bar('Clip · extremo',(76,-2),(78,-7),2.7,1.6,steel,7)

# Set a useful camera/light in addition to the model's default view.
bpy.ops.object.light_add(type='AREA', location=(0,-90,120)); bpy.context.object.data.energy=900; bpy.context.object.data.shape='DISK'; bpy.context.object.data.size=90
bpy.ops.object.camera_add(location=(145,-190,125)); cam=bpy.context.object; cam.data.lens=55; cam.rotation_euler=(Vector(( -15,0,0))-cam.location).to_track_quat('-Z','Y').to_euler(); bpy.context.scene.camera=cam
scene=bpy.context.scene; scene.render.engine='BLENDER_EEVEE'; scene.render.resolution_x=1200; scene.render.resolution_y=800; scene.render.resolution_percentage=100
scene.world.color=(.12,.12,.12)
explode='--explode' in sys.argv
if explode:
    for o in bpy.context.scene.objects:
        n=o.name.lower()
        if any(s in n for s in ('clip','anclaje')): o.location.x += 34
        elif any(s in n for s in ('pulsador','tapa trasera','corona')): o.location.x += 25
        elif 'resorte' in n or 'guía del resorte' in n: o.location.x += 15
        elif any(s in n for s in ('cartucho','depósito de tinta','punta del cartucho')): o.location.x += 8
        elif any(s in n for s in ('agarre','estría')): o.location.x -= 8
        elif any(s in n for s in ('punta cónica','cono frontal')): o.location.x -= 16
filename='lapicero-exploded.glb' if explode else 'lapicero.glb'
bpy.ops.export_scene.gltf(filepath=bpy.path.abspath('//'+filename),export_format='GLB',export_apply=True,export_cameras=False,export_lights=False)
