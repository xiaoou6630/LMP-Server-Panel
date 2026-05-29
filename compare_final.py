import os

# 对比 LMP 生成的和我们生成的
config_dir = 'e:/daima/ml/tools/lmp_server/LMPServer/Config'
backup_dir = os.path.join(config_dir, 'backup_lmp')

for fname in ['GeneralSettings.xml']:
    lmp_path = os.path.join(backup_dir, fname)
    our_path = os.path.join(config_dir, fname)
    
    if not os.path.exists(lmp_path) or not os.path.exists(our_path):
        print(f'文件不存在')
        continue
    
    lmp_data = open(lmp_path, 'rb').read()
    our_data = open(our_path, 'rb').read()
    
    print(f'=== {fname} 对比 ===')
    print(f'LMP: {len(lmp_data)} bytes')
    print(f'我们: {len(our_data)} bytes')
    
    lmp_text = lmp_data.decode('utf-8')
    our_text = our_data.decode('utf-8')
    
    lmp_lines = lmp_text.split('\r\n')
    our_lines = our_text.split('\r\n')
    
    print(f'LMP 行数: {len(lmp_lines)}')
    print(f'我们行数: {len(our_lines)}')
    
    # 逐行对比
    max_lines = max(len(lmp_lines), len(our_lines))
    for i in range(max_lines):
        lmp_line = lmp_lines[i] if i < len(lmp_lines) else None
        our_line = our_lines[i] if i < len(our_lines) else None
        
        if lmp_line != our_line:
            print(f'\n第 {i+1} 行不同:')
            print(f'  LMP:  {repr(lmp_line)}')
            print(f'  我们: {repr(our_line)}')
            
            if i >= 10:
                print('  ... (只显示前 10 行差异)')
                break
