"""Interactive 2D truck-mounted crane schematic. No external packages needed."""
import math
import time
from operation_simulation import simulation_values
import tkinter as tk
from tkinter import ttk
from crane_can import VehicleTransmitter
from fms_can import tire_interval

WIDTH, HEIGHT = 1000, 540
GROUND_Y = 415

root = tk.Tk()
root.title('Truck and Crane — Tkinter Canvas Demo')
# Set the final window geometry after all controls have been laid out.
# This avoids an unused strip between the drawing and the sliders.

angle = tk.DoubleVar(value=35)
extension = tk.DoubleVar(value=35)
pressure = tk.DoubleVar(value=160)
slew = tk.DoubleVar(value=0)       # Slewing angle, in degrees
load_kg = tk.DoubleVar(value=0)      # Load in 100 kg increments
engine = {
    'RPM': tk.DoubleVar(value=1250),
    'Oil temp': tk.DoubleVar(value=88),
    'Oil pressure': tk.DoubleVar(value=4.2),
    'Coolant temp': tk.DoubleVar(value=85),
    'Coolant pressure': tk.DoubleVar(value=1.5),
    'Wheel based speed': tk.DoubleVar(value=60),
    'Engine running time': tk.DoubleVar(value=300),
}

# Tire telemetry is kept separately for each wheel (bar and degrees Celsius).
wheel_positions = (180, 275, 545, 675)
wheel_names = ('Rear 1', 'Rear 2', 'Front 1', 'Front 2')
wheel_data = {name: {'pressure': 8.0, 'temperature': 35.0} for name in wheel_names}
selected_wheel = tk.StringVar(value=wheel_names[0])
wheel_pressure = tk.DoubleVar(value=8.0)
wheel_temperature = tk.DoubleVar(value=35.0)
changing_selection = False
tire_send_seconds = tk.StringVar(value='10')
last_tire_interval = 10.0

canvas = tk.Canvas(root, width=WIDTH, height=HEIGHT, bg='#e9f2fa', highlightthickness=0)
# Keep the drawing area at its designed height; do not expand into spare space.
canvas.pack(padx=12, pady=(8, 5), fill='x', expand=False)

controls = ttk.Frame(root, padding=(10, 3, 10, 8))
controls.pack(fill='x')

def draw():
    canvas.delete('all')
    canvas.create_rectangle(0, GROUND_Y, WIDTH, HEIGHT, fill='#d4e0d0', outline='')
    canvas.create_line(0, GROUND_Y, WIDTH, GROUND_Y, fill='#637482', width=3)
    canvas.create_text(25, 18, text='TRUCK + CRANE SIMULATOR', anchor='nw', fill='#253c53', font=('Arial', 18, 'bold'))

    # Truck chassis, bed and front cabin.
    canvas.create_rectangle(110, 345, 715, 392, fill='#465e79', outline='#263747', width=3)
    canvas.create_rectangle(115, 328, 490, 349, fill='#748ca0', outline='#263747', width=2)
    canvas.create_polygon(600, 350, 600, 288, 645, 260, 719, 260, 757, 311, 757, 390, 600, 390,
                          fill='#efb13c', outline='#80531d', width=3)
    canvas.create_polygon(652, 271, 706, 271, 738, 310, 652, 310, fill='#b6d9e9', outline='#546b78', width=2)
    canvas.create_line(650, 314, 650, 386, fill='#9b6a20', width=2)
    canvas.create_rectangle(744, 338, 760, 367, fill='#313f4a', outline='')
    # Tire shape and color respond to independently simulated telemetry.
    # 8 bar = nominal. Lower pressure reduces height and widens the footprint.
    for i, x in enumerate(wheel_positions):
        name = wheel_names[i]
        tire_p = wheel_data[name]['pressure']
        tire_t = wheel_data[name]['temperature']
        flatness = max(0.0, min(1.0, (8.0 - tire_p) / 7.0))
        tire_half_width = 30 + 12 * flatness
        tire_height = 60 - 32 * flatness
        bottom = GROUND_Y + 6
        top = bottom - tire_height
        # Temperature and pressure both influence warning colors.
        color = ('#bd3030' if tire_p < 4.0 or tire_t >= 90 else
                 '#e89b24' if tire_p < 6.5 or tire_t >= 70 else '#27303b')
        canvas.create_oval(x-tire_half_width, top, x+tire_half_width, bottom,
                           fill=color, outline='#111821', width=3)
        center_y = (top + bottom) / 2
        hub_r = max(7, 13 - 5 * flatness)
        canvas.create_oval(x-hub_r, center_y-hub_r, x+hub_r, center_y+hub_r,
                           fill='#c5ced5', outline='#6e7e89', width=2)
        canvas.create_text(x, GROUND_Y+31, text=f'{name}: {tire_p:.1f} bar',
                           font=('Arial', 9, 'bold'), fill=color if color != '#27303b' else '#253c53')
        canvas.create_text(x, GROUND_Y+47, text=f'{tire_t:.0f}°C',
                           font=('Arial', 9), fill='#253c53')

    # Outrigger / stabilizer.
    canvas.create_rectangle(350, 360, 365, 412, fill='#7b8792', outline='#334454', width=2)
    canvas.create_rectangle(327, 409, 388, 416, fill='#596d7e', outline='#334454')

    # Crane pedestal and articulated boom.
    px, py = 415, 329
    canvas.create_rectangle(392, 316, 447, 353, fill='#dc9c2f', outline='#7e5721', width=3)
    a = math.radians(float(angle.get()))
    length = 170 + float(extension.get()) * 2.6
    tipx = px - length * math.cos(a)
    tipy = py - length * math.sin(a)

    # Main boom as a thick vector line, with telescoping section in a lighter color.
    midx = px - 172 * math.cos(a)
    midy = py - 172 * math.sin(a)
    canvas.create_line(px, py, midx, midy, fill='#b57616', width=26, capstyle=tk.ROUND)
    canvas.create_line(px, py, midx, midy, fill='#e5a537', width=20, capstyle=tk.ROUND)
    canvas.create_line(midx, midy, tipx, tipy, fill='#e5bb62', width=14, capstyle=tk.ROUND)
    canvas.create_oval(px-10, py-10, px+10, py+10, fill='#455465', outline='#253443', width=2)

    # Hydraulic cylinder, connected to a point partway along the boom.
    cx = px - 92 * math.cos(a)
    cy = py - 92 * math.sin(a)
    canvas.create_line(455, 363, cx, cy, fill='#56758b', width=12)
    canvas.create_line(455, 363, cx, cy, fill='#bfd5dd', width=5)

    # Hook hangs vertically from the end of the boom.
    hook_y = min(tipy + 70, GROUND_Y - 12)
    canvas.create_line(tipx, tipy, tipx, hook_y, fill='#424950', width=2)
    canvas.create_arc(tipx-9, hook_y-4, tipx+9, hook_y+15, start=170, extent=220,
                      style=tk.ARC, outline='#2c3744', width=4)

    # Suspended load: 0-10,000 kg (exactly 100 kg per slider step).
    mass = int(load_kg.get())
    if mass:
        # Enlarges with mass, with a constant gap below the hook.
        box_w = 22 + 46 * (mass / 10000)
        box_h = 14 + 29 * (mass / 10000)
        left, top = tipx - box_w / 2, hook_y + 15
        canvas.create_line(tipx, hook_y+11, tipx, top, fill='#495462', width=2)
        load_fill = '#d7ac43' if mass < 8000 else '#cd693e'
        canvas.create_rectangle(left, top, left+box_w, top+box_h,
                                fill=load_fill, outline='#624c2e', width=2)
        canvas.create_text(tipx, top + box_h / 2, text=f'{mass/1000:.1f}t',
                           fill='#263544', font=('Arial', 9, 'bold'))

    p = float(pressure.get())
    status_color = '#268b48' if p < 220 else '#d58a18' if p < 280 else '#c0392b'
    canvas.create_oval(790, 65, 809, 84, fill=status_color, outline='#3d4a55')
    canvas.create_text(819, 75, anchor='w', text=f'Hydraulic: {p:.0f} bar',
                       font=('Arial', 11, 'bold'), fill='#253c53')
    canvas.create_text(792, 100, anchor='w',
                       text=f'Boom: {angle.get():.0f}°   Extension: {extension.get():.0f}%',
                       font=('Arial', 10), fill='#253c53')
    canvas.create_text(792, 125, anchor='w', text=f'Load: {load_kg.get()/1000:.1f} t  ({load_kg.get():,} kg)',
                       font=('Arial', 11, 'bold'), fill='#253c53')

    # Top-down crane slewing indicator. Boom arrow rotates relative to truck axis.
    sx, sy, radius = 842, 188, 40
    canvas.create_text(sx, 140, text='SLEW (TOP VIEW)', fill='#253c53',
                       font=('Arial', 9, 'bold'))
    canvas.create_oval(sx-radius, sy-radius, sx+radius, sy+radius,
                       outline='#8298a9', width=2, fill='#f8fbfc')
    canvas.create_rectangle(sx-9, sy-27, sx+9, sy+27, fill='#9baebb', outline='#52667a')
    canvas.create_line(sx, sy-radius+5, sx, sy+radius-5, fill='#d1dae1', dash=(3,3))
    theta = math.radians(float(slew.get())-90)
    tip_sx = sx+radius*0.85*math.cos(theta)
    tip_sy = sy+radius*0.85*math.sin(theta)
    canvas.create_line(sx, sy, tip_sx, tip_sy, fill='#d78c26', width=6,
                       arrow=tk.LAST, arrowshape=(9, 11, 5))
    canvas.create_oval(sx-5, sy-5, sx+5, sy+5, fill='#394e62', outline='')
    canvas.create_text(906, 187, anchor='w', text=f'{slew.get():.0f}°',
                       font=('Arial', 15, 'bold'), fill='#253c53')

    # Engine block schematic and per-parameter mini gauges with warning colors.
    canvas.create_rectangle(778, 252, 993, 498, fill='#fff', outline='#b6c7d5')
    canvas.create_text(790, 263, anchor='nw', text='ENGINE / LIVE PARAMETERS',
                       font=('Arial', 10, 'bold'), fill='#253c53')
    # A small, programmatically drawn engine silhouette.
    canvas.create_rectangle(790, 290, 849, 318, fill='#60798d', outline='#344a5e', width=2)
    canvas.create_rectangle(801, 282, 838, 290, fill='#7e96a9', outline='#344a5e')
    for k in range(3):
        canvas.create_line(802+14*k, 282, 802+14*k, 290, fill='#334a5c', width=2)
    canvas.create_oval(803, 316, 818, 331, fill='#d8e1e8', outline='#536879', width=2)
    canvas.create_oval(826, 316, 841, 331, fill='#d8e1e8', outline='#536879', width=2)
    canvas.create_line(849, 302, 861, 302, 861, 289, fill='#61798d', width=5)
    canvas.create_text(870, 305, anchor='w', text=f'{engine["RPM"].get():.0f} RPM',
                       font=('Arial', 12, 'bold'),
                       fill='#c0392b' if engine['RPM'].get() >= 3000 else '#253c53')

    # Bars indicate the relative value in each sensor's range (not physical engine components).
    rows = [
        ('Oil temp', 0, 160, '°C', 115, 135),
        ('Oil pressure', 0, 10, 'bar', 2, 1),  # Low values are warning/critical
        ('Coolant temp', 0, 130, '°C', 105, 115),
        ('Coolant pressure', 0, 4, 'bar', 1.0, 1.0),
        ('Wheel based speed', 0, 120, 'km/h', None, None),
        ('Engine running time', 0, 5000, 'h', None, None),
    ]
    for i, (key, low, high, unit, warning, critical) in enumerate(rows):
        y = 345 + 26*i
        v = engine[key].get()
        if warning is None:
            color = '#2b9c67'
        elif key == 'Oil pressure':
            color = '#c0392b' if v <= critical else '#dc9a23' if v <= warning else '#2b9c67'
        elif key == 'Coolant pressure':
            color = '#c0392b' if v < 1.0 else '#2b9c67'
        else:
            color = '#c0392b' if v >= critical else '#dc9a23' if v >= warning else '#2b9c67'
        label = 'Running time' if key == 'Engine running time' else key
        canvas.create_text(791, y, text=label, anchor='w', fill='#364d60', font=('Arial', 9))
        canvas.create_text(987, y, text=f'{v:.1f} {unit}' if 'pressure' in key.lower() else f'{v:.0f} {unit}',
                           anchor='e', fill=color, font=('Arial', 9, 'bold'))
        canvas.create_rectangle(791, y+11, 986, y+19, fill='#e4ebf0', outline='')
        canvas.create_rectangle(791, y+11, 791+195*max(0,min(1,(v-low)/(high-low))), y+19,
                                fill=color, outline='')
    canvas.create_text(25, HEIGHT-22, anchor='w', text='All graphics are generated by Tkinter Canvas — no truck image is loaded.',
                       fill='#496274', font=('Arial', 10))


# Compact controls: labels and live values sit immediately before each slider.
# The sliders are intentionally short, allowing everything to fit on one screen.
metric_refreshers = []


def metric_slider(parent, row, name, variable, low, high, unit='', digits=0,
                  callback=None, slider_width=125):
    ttk.Label(parent, text=name, width=17, anchor='w').grid(row=row, column=0, sticky='w', pady=2)
    readout = ttk.Label(parent, width=12, anchor='e')
    readout.grid(row=row, column=1, sticky='e', padx=(0, 5))

    def changed(_value=None, redraw=True):
        value = variable.get()
        readout.configure(text=f'{value:.{digits}f} {unit}'.strip())
        if not redraw:
            return
        if callback:
            callback()
        else:
            draw()

    scale = ttk.Scale(parent, from_=low, to=high, variable=variable,
                      command=changed, length=slider_width)
    scale.grid(row=row, column=2, sticky='ew', padx=(0, 5))
    parent.columnconfigure(2, weight=1)
    changed()
    metric_refreshers.append(changed)
    return changed


def on_tire_change():
    name = selected_wheel.get()
    wheel_data[name]['pressure'] = wheel_pressure.get()
    wheel_data[name]['temperature'] = wheel_temperature.get()
    draw()


def on_select_wheel(_event=None):
    # Variable updates don't invoke ttk.Scale's command, so explicitly refresh labels.
    readings = wheel_data[selected_wheel.get()]
    wheel_pressure.set(readings['pressure'])
    wheel_temperature.set(readings['temperature'])
    update_tire_p()
    update_tire_t()
    draw()


def set_flat():
    wheel_pressure.set(1.0)
    update_tire_p()


def reset_tire():
    wheel_pressure.set(8.0)
    wheel_temperature.set(35.0)
    update_tire_p()
    update_tire_t()


crane_panel = ttk.LabelFrame(controls, text='Crane', padding=7)
crane_panel.grid(row=0, column=0, sticky='nsew', padx=4)
metric_slider(crane_panel, 0, 'Boom angle', angle, 0, 70, '°')
metric_slider(crane_panel, 1, 'Extension', extension, 0, 100, '%')
metric_slider(crane_panel, 2, 'Hydraulic pressure', pressure, 0, 320, 'bar')
metric_slider(crane_panel, 3, 'Slew', slew, 0, 360, '°')
# ttk.Scale is continuous; snap to precisely 100 kg for every change.
def snap_load(_value=None):
    rounded = max(0, min(10000, round(float(_value if _value is not None else load_kg.get()) / 100) * 100))
    if rounded != load_kg.get():
        load_kg.set(rounded)
    load_readout.configure(text=f'{rounded/1000:.1f} t')
    draw()
ttk.Label(crane_panel, text='Load', width=17, anchor='w').grid(row=4, column=0, sticky='w', pady=2)
load_readout = ttk.Label(crane_panel, width=12, anchor='e', text='0.0 t')
load_readout.grid(row=4, column=1, sticky='e', padx=(0, 5))
# Use the same compact ttk.Scale style as all other parameters.
# The callback snaps the continuous scale onto 100 kg increments.
load_slider = ttk.Scale(crane_panel, from_=0, to=10000,
                        variable=load_kg, command=snap_load, length=125)
load_slider.grid(row=4, column=2, sticky='ew', padx=(0, 5))

tire_panel = ttk.LabelFrame(controls, text='Tires (select wheel)', padding=7)
tire_panel.grid(row=0, column=1, sticky='nsew', padx=4)
selector = ttk.Combobox(tire_panel, textvariable=selected_wheel,
                        values=wheel_names, state='readonly', width=17)
selector.grid(row=0, column=0, columnspan=3, sticky='w', pady=(0, 4))
selector.bind('<<ComboboxSelected>>', on_select_wheel)
update_tire_p = metric_slider(tire_panel, 1, 'Pressure', wheel_pressure,
                              0, 10, 'bar', digits=1, callback=on_tire_change)
update_tire_t = metric_slider(tire_panel, 2, 'Temperature', wheel_temperature,
                              0, 120, '°C', callback=on_tire_change)
buttons = ttk.Frame(tire_panel)
buttons.grid(row=3, column=0, columnspan=3, sticky='w', pady=(5, 0))
ttk.Button(buttons, text='Simulate flat', command=set_flat).pack(side='left', padx=(0, 5))
ttk.Button(buttons, text='Reset wheel', command=reset_tire).pack(side='left')

ttk.Label(tire_panel, text='Send interval (sec)').grid(row=4, column=0, sticky='w', pady=(6, 0))
interval_input = ttk.Spinbox(tire_panel, from_=0.1, to=3600, increment=1,
                             textvariable=tire_send_seconds, width=9)
interval_input.grid(row=4, column=1, columnspan=2, sticky='w', pady=(6, 0))
interval_hint = ttk.Label(tire_panel, text='One tire per interval · CAN1', foreground='#526579')
interval_hint.grid(row=5, column=0, columnspan=3, sticky='w', pady=(3, 0))

engine_panel = ttk.LabelFrame(controls, text='Engine', padding=7)
engine_panel.grid(row=0, column=2, sticky='nsew', padx=4)
for row, (key, lo, hi, unit, digits) in enumerate([
    ('RPM', 0, 4000, 'rpm', 0),
    ('Oil temp', 0, 160, '°C', 0),
    ('Oil pressure', 0, 10, 'bar', 1),
    ('Coolant temp', 0, 130, '°C', 0),
    ('Coolant pressure', 0, 4, 'bar', 1),
    ('Wheel based speed', 0, 120, 'km/h', 0),
    ('Engine running time', 0, 5000, 'h', 0),
]):
    label = 'Running time' if key == 'Engine running time' else key
    metric_slider(engine_panel, row, label, engine[key], lo, hi, unit, digits, slider_width=110)

for col in range(3):
    controls.columnconfigure(col, weight=1)

can_panel = ttk.Frame(root, padding=(14, 0, 14, 10))
can_panel.pack(fill='x')
can_status = tk.StringVar(value='Disconnected · GCAN-II CAN1 engine/tires + CAN2 crane · 250 kbps')
transmitter = None
closing = False


def engine_snapshot():
    global last_tire_interval
    try:
        last_tire_interval = tire_interval(tire_send_seconds.get())
        interval_hint.configure(text='One tire per interval · CAN1', foreground='#526579')
    except ValueError:
        interval_hint.configure(text=f'Enter seconds > 0; using {last_tire_interval:g} sec',
                                foreground='#bd3030')
    return {**{key: variable.get() for key, variable in engine.items()},
            'angle': angle.get(), 'extension': extension.get(),
            'pressure': pressure.get(), 'slew': slew.get(), 'load_kg': load_kg.get(),
            'wheels': {name: dict(readings) for name, readings in wheel_data.items()},
            'tire_interval': last_tire_interval}


def toggle_can():
    global transmitter
    if transmitter is not None and transmitter.thread.is_alive():
        transmitter.stop()
        connect_button.configure(state='disabled')
        can_status.set('Disconnecting…')
    else:
        transmitter = VehicleTransmitter(engine_snapshot())
        transmitter.start()
        connect_button.configure(text='Disconnect GCAN-II')
        can_status.set('Connecting to GCAN-II…')


def poll_can():
    if transmitter is not None:
        transmitter.update(engine_snapshot())
        state, message = transmitter.status()
        if transmitter.thread.is_alive():
            if connect_button['state'] != 'disabled':
                can_status.set(message)
        else:
            can_status.set(message)
            connect_button.configure(text='Connect GCAN-II', state='normal')
    if closing:
        if transmitter is None or not transmitter.thread.is_alive():
            root.destroy()
            return
    root.after(50, poll_can)


def close_window():
    global closing
    closing = True
    stop_simulation()
    connect_button.configure(state='disabled')
    if transmitter is not None:
        transmitter.stop()
    # Poll for worker cleanup without blocking Tk or closing the DLL during a send.


simulation_job = None
simulation_started = None
simulation_initial_hours = 300
simulation_status = tk.StringVar(value='Manual controls')


def stop_simulation():
    global simulation_job, simulation_started
    if simulation_job is not None:
        root.after_cancel(simulation_job)
        simulation_job = None
    simulation_started = None
    simulation_button.configure(text='Simulation: OFF')
    simulation_status.set('Manual controls')


def simulation_tick():
    global simulation_job
    simulation_job = None
    if closing or simulation_started is None:
        return
    values, wheels, phase = simulation_values(
        time.monotonic() - simulation_started, simulation_initial_hours)
    for key, variable in engine.items():
        variable.set(values[key])
    for key, variable in [('angle', angle), ('extension', extension),
                          ('pressure', pressure), ('slew', slew), ('load_kg', load_kg)]:
        variable.set(values[key])
    for name, readings in wheels.items():
        wheel_data[name].update(readings)
    selected = wheel_data[selected_wheel.get()]
    wheel_pressure.set(selected['pressure'])
    wheel_temperature.set(selected['temperature'])
    for refresh in metric_refreshers:
        refresh(redraw=False)
    load_readout.configure(text=f'{load_kg.get()/1000:.1f} t')
    simulation_status.set(f'Simulation · {phase}')
    draw()
    simulation_job = root.after(100, simulation_tick)


def toggle_simulation():
    global simulation_started, simulation_initial_hours
    if simulation_started is not None:
        stop_simulation()
    elif not closing:
        simulation_initial_hours = engine['Engine running time'].get()
        simulation_started = time.monotonic()
        simulation_button.configure(text='Simulation: ON')
        simulation_tick()


simulation_panel = ttk.Frame(root, padding=(14, 0, 14, 8))
simulation_panel.pack(fill='x', before=can_panel)
simulation_button = ttk.Button(simulation_panel, text='Simulation: OFF', command=toggle_simulation)
simulation_button.pack(side='left', padx=(0, 12))
ttk.Label(simulation_panel, textvariable=simulation_status).pack(side='left')


connect_button = ttk.Button(can_panel, text='Connect GCAN-II', command=toggle_can)
connect_button.pack(side='left', padx=(0, 12))
ttk.Label(can_panel, textvariable=can_status, wraplength=850).pack(side='left')
root.protocol('WM_DELETE_WINDOW', close_window)
root.after(50, poll_can)

# Ask Tkinter for the height actually needed by the canvas and three control panels.
# Start with a tightly fitted window, rather than a fixed 800 px tall one.
root.update_idletasks()
root.geometry(f'1120x{root.winfo_reqheight()}')
root.minsize(1050, root.winfo_reqheight())

draw()
root.mainloop()
