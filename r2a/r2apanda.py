#UnB TR2 - 2020/1
#Grupo 15
#Augusto Freitas Brandão - 16/0024366
#Fernando Sobral Nóbrega - 15/0034911


from r2a.ir2a import IR2A
from player.parser import *
import time

class R2APanda(IR2A):

    def __init__(self, id):
        IR2A.__init__(self, id)
        self.calculated = 0        # calculated target throughputs (x^)
        self.smoothed = 0          # smoothed troughputs (y^)
        self.measured = 0          # real measured throughputs (x~)
        self.quantized = 0         # quantized troughputs (r)
        self.video_seg_time = 1     # each segment time has 1s of duration (tau)
        self.actual_inter_request_time = 0 # (T)
        self.schedule = 0           # time between segments downloads (T^)
        self.download_time = 0      # segment download duration (T~)
        self.request_time = 0       
        self.qi = []                # video quality index


    def handle_xml_request(self, msg):
        self.request_time = time.perf_counter()
        self.send_down(msg)

    def handle_xml_response(self, msg):

        parsed_mpd = parse_mpd(msg.get_payload())
        self.qi = parsed_mpd.get_qi()

        download_time = time.perf_counter() - self.request_time

        # first iteraction
        if self.measured == 0:
            self.measured = msg.get_bit_length() / download_time

        self.send_up(msg)


    def handle_segment_size_request(self, msg):
        self.request_time = time.perf_counter()

        self.calculated = self.target_throughput()
        self.smoothed = self.smoothed_throughput()
        self.quantized = self.select_qi()

        msg.add_quality_id(self.quantized)

        self.send_down(msg)

    def handle_segment_size_response(self, msg):

        self.schedule_handler()
        download_time = time.perf_counter() - self.request_time

        self.actual_inter_request_time = max(self.schedule, download_time)
        self.measured = msg.get_bit_length() / download_time

        self.send_up(msg)

    def initialize(self):
        pass

    def finalization(self):
        pass


    def target_throughput(self):
        k = 0.14                # probing convergence rate
        w = 0.3 * 1048576       # probing additive increace megabitrate

        if self.calculated != 0:
            x = (k * (w - max(0, self.calculated - self.measured + w)) 
                * self.actual_inter_request_time + self.calculated)
            return x

        x = self.measured       # first interaction
        
        return x


    def smoothed_throughput(self):
        alpha = 0.2             # smoothing convergence rate

        if self.smoothed != 0:
            y = abs(-alpha * (self.smoothed - self.calculated) 
                    * self.actual_inter_request_time + self.smoothed)
            return y
        
        y = self.measured    # first interaction

        return y


    def select_qi(self):
        E = 0.15                # multiplicative safety margin
        r_up = self.qi[0]       # upshift threshold for dead-zone in quantization
        r_down = self.qi[0]     # dowmshift threshold for dead-zone in quantization
        initial_r_up = self.smoothed * (1 - E)
        initial_r_down = self.smoothed

        for quaity in self.qi:
            if initial_r_up > quaity:
                r_up = quaity
            if initial_r_down > quaity:
                r_down = quaity
        
        # updates dead-zone quantizier
        if self.quantized == 0:
            return r_down
        elif self.quantized < r_up:
            return r_up
        elif r_up <= self.quantized < r_down:
            return self.quantized
        
        return r_down

    
    def schedule_handler(self):
        B_min = 26          # minimum client buffer duration
        beta = 0.2          # client buffer convergence duration
        B = self.whiteboard.get_amount_video_to_play()  # client buffer duration

        self.schedule = self.quantized * self.video_seg_time / self.smoothed + beta * (B - B_min)
        