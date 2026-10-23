"""Pure-Python FLAC boundary parser. 纯 Python FLAC 帧边界、Rice 残差与 CRC 检查。"""


def make_crc_table(polynomial, width):
    table = []
    mask = (1 << width) - 1
    for value in range(256):
        checksum = value << (width - 8)
        for _ in range(8):
            checksum = ((checksum << 1) ^ (polynomial if checksum & (1 << (width - 1)) else 0)) & mask
        table.append(checksum)
    return table


CRC8_TABLE = make_crc_table(0x07, 8)
CRC16_TABLE = make_crc_table(0x8005, 16)


def crc8(data):
    checksum = 0
    for value in data:
        checksum = CRC8_TABLE[checksum ^ value]
    return checksum


def crc16(data):
    checksum = 0
    for value in data:
        checksum = ((checksum << 8) & 65535) ^ CRC16_TABLE[(checksum >> 8) ^ value]
    return checksum


class BitReader:
    def __init__(self, data, position):
        self.data = data
        self.position = position

    def read(self, count):
        if count < 0 or self.position + count > len(self.data) * 8:
            raise ValueError("truncated FLAC frame")
        value = 0
        while count:
            byte_index, bit_index = divmod(self.position, 8)
            amount = min(count, 8 - bit_index)
            value = (value << amount) | ((self.data[byte_index] >> (8 - bit_index - amount)) & ((1 << amount) - 1))
            self.position += amount
            count -= amount
        return value

    def skip(self, count):
        if count < 0 or self.position + count > len(self.data) * 8:
            raise ValueError("truncated FLAC frame")
        self.position += count

    def unary(self):
        # Rice quotient: zeros followed by one. / Rice 商由若干零和终止位一组成。
        while self.position < len(self.data) * 8:
            byte_index, bit_index = divmod(self.position, 8)
            value = self.data[byte_index] & ((1 << (8 - bit_index)) - 1)
            if value:
                self.position += 8 - bit_index - value.bit_length() + 1
                return
            self.position += 8 - bit_index
        raise ValueError("truncated FLAC Rice code")


def residual(reader, block_size, predictor_order):
    method = reader.read(2)
    if method > 1:
        raise ValueError("reserved FLAC residual method")
    parameter_bits = 4 + method
    partitions = 1 << reader.read(4)
    if block_size % partitions:
        raise ValueError("invalid FLAC partition")
    for index in range(partitions):
        count = block_size // partitions - (predictor_order if index == 0 else 0)
        if count < 0:
            raise ValueError("invalid predictor order")
        parameter = reader.read(parameter_bits)
        if parameter == (1 << parameter_bits) - 1:
            reader.skip(count * reader.read(5))
        else:
            for _ in range(count):
                reader.unary()
                reader.skip(parameter)


def frame_size(data, stream_bits, stream_channels, expected_number, samples_seen):
    if len(data) < 8 or data[0] != 255 or data[1] & 254 != 248 or data[3] & 1:
        raise ValueError("invalid FLAC sync")
    block_code, rate_code = data[2] >> 4, data[2] & 15
    channels_code, bits_code = data[3] >> 4, (data[3] >> 1) & 7
    if not block_code or rate_code == 15 or channels_code > 10 or bits_code == 3:
        raise ValueError("reserved FLAC header")
    channels = channels_code + 1 if channels_code <= 7 else 2
    bits = {0: stream_bits, 1: 8, 2: 12, 4: 16, 5: 20, 6: 24, 7: 32}[bits_code]
    if channels != stream_channels or bits != stream_bits:
        raise ValueError("FLAC stream parameters changed")
    position = 4
    first = data[position]
    position += 1
    if first < 128:
        number = first
    else:
        width = 0
        marker = 128
        while first & marker:
            width += 1
            marker >>= 1
        if not 2 <= width <= 7 or position + width - 1 > len(data):
            raise ValueError("invalid FLAC frame number")
        number = first & ((1 << (7 - width)) - 1)
        for _ in range(width - 1):
            value = data[position]
            position += 1
            if value & 192 != 128:
                raise ValueError("invalid FLAC frame number")
            number = (number << 6) | (value & 63)
    if number != (samples_seen if data[1] & 1 else expected_number):
        raise ValueError("non-contiguous FLAC frames")
    if block_code == 1:
        block_size = 192
    elif 2 <= block_code <= 5:
        block_size = 576 << (block_code - 2)
    elif block_code == 6:
        block_size = data[position] + 1
        position += 1
    elif block_code == 7:
        block_size = int.from_bytes(data[position:position + 2], "big") + 1
        position += 2
    else:
        block_size = 256 << (block_code - 8)
    position += {12: 1, 13: 2, 14: 2}.get(rate_code, 0)
    if position >= len(data) or crc8(data[:position + 1]):
        raise ValueError("FLAC header CRC failed")
    reader = BitReader(data, (position + 1) * 8)
    for channel in range(channels):
        channel_bits = bits + int((channels_code in (8, 10) and channel == 1)
                                  or (channels_code == 9 and channel == 0))
        if reader.read(1):
            raise ValueError("invalid subframe padding")
        kind = reader.read(6)
        if reader.read(1):
            wasted_start = reader.position
            reader.unary()
            channel_bits -= reader.position - wasted_start
            if channel_bits <= 0:
                raise ValueError("invalid wasted bits")
        if kind == 0:
            reader.skip(channel_bits)
        elif kind == 1:
            reader.skip(block_size * channel_bits)
        elif 8 <= kind <= 12:
            order = kind - 8
            if order > block_size:
                raise ValueError("invalid fixed predictor")
            reader.skip(order * channel_bits)
            residual(reader, block_size, order)
        elif 32 <= kind <= 63:
            order = kind - 31
            if order > block_size:
                raise ValueError("invalid LPC predictor")
            reader.skip(order * channel_bits)
            precision = reader.read(4) + 1
            if precision == 16:
                raise ValueError("invalid LPC precision")
            reader.skip(5 + order * precision)
            residual(reader, block_size, order)
        else:
            raise ValueError("reserved FLAC subframe")
    padding = (-reader.position) % 8
    if reader.read(padding):
        raise ValueError("nonzero FLAC padding")
    length = reader.position // 8 + 2
    if length > len(data) or crc16(data[:length]):
        raise ValueError("FLAC frame CRC failed")
    return length, block_size


def flac(image, start, limit):
    end = min(image.size, start + limit)
    position = start + 4
    stream_info = None
    while position + 4 <= end:
        header = image.read(position, 4)
        kind = header[0] & 127
        length = int.from_bytes(header[1:4], "big")
        if kind == 127 or position + 4 + length > end:
            return None
        if stream_info is None:
            if kind != 0 or length != 34:
                return None
            stream_info = image.read(position + 4, 34)
        elif kind == 0:
            return None
        position += 4 + length
        if header[0] & 128:
            break
    else:
        return None
    packed = int.from_bytes(stream_info[10:18], "big")
    rate, channels, bits = packed >> 44, ((packed >> 41) & 7) + 1, ((packed >> 36) & 31) + 1
    total_samples = packed & ((1 << 36) - 1)
    maximum_block = int.from_bytes(stream_info[2:4], "big")
    maximum_frame = int.from_bytes(stream_info[7:10], "big")
    if not rate or not total_samples or not maximum_block or bits < 4:
        return None
    maximum_read = maximum_frame or (maximum_block * channels * (bits + 1) // 8 + 65536)
    samples_seen = frame_number = 0
    try:
        while samples_seen < total_samples:
            data = image.read(position, min(maximum_read, end - position))
            length, block_size = frame_size(data, bits, channels, frame_number, samples_seen)
            if block_size > maximum_block or samples_seen + block_size > total_samples:
                return None
            samples_seen += block_size
            position += length
            frame_number += 1
    except (ValueError, IndexError, KeyError):
        return None
    return position - start, "flac", "flac_metadata_subframes_and_crc"
