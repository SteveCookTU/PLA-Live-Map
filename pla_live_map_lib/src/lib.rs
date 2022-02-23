mod xoroshiro;

use std::collections::HashMap;
use pyo3::prelude::*;
use crate::xoroshiro::Xoroshiro;

#[pymodule]
fn pla_live_map_lib(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(calc_from_seed_py, m)?)?;
    m.add_function(wrap_pyfunction!(generate_from_seed, m)?)?;
    m.add_function(wrap_pyfunction!(find_slots_py, m)?)?;
    m.add_function(wrap_pyfunction!(slot_to_pokemon_py, m)?)?;
    m.add_function(wrap_pyfunction!(next_filtered_py, m)?)?;
    m.add_function(wrap_pyfunction!(generate_passive_search_paths, m)?)?;
    Ok(())
}

fn slot_to_pokemon(values: HashMap<String, f64>, mut slot: f64) -> String {
    for (pokemon, slot_val) in values {
        if slot <= slot_val {
            return pokemon;
        }
        slot -= slot_val
    }
    "".to_string()
}

#[pyfunction]
#[pyo3(name = "slot_to_pokemon")]
fn slot_to_pokemon_py(values: HashMap<String, f64>, slot: f64) -> PyResult<String> {

    Ok(slot_to_pokemon(values, slot))
}

fn find_slots(time: &str, weather: &str, sp_slots: HashMap<String, HashMap<String, f64>>) -> HashMap<String, f64> {
    let result = sp_slots.iter().filter(|(time_weather, _)| {
        let slot_params = time_weather.split("/").collect::<Vec<&str>>();
        vec![time, "Any Time"].contains(&slot_params[0]) && vec![weather, "All Weather"].contains(&slot_params[1])
    }).next();

    match result {
        Some((_, values)) => values.to_owned(),
        None => HashMap::new()
    }

}

#[pyfunction]
#[pyo3(name = "find_slots")]
fn find_slots_py(time: &str, weather: &str, sp_slots: HashMap<String, HashMap<String, f64>>) -> PyResult<HashMap<String, f64>> {
    let map = find_slots(time, weather, sp_slots);
    Ok(map)
}

fn next_filtered(group_seed: u64, rolls: u8, guaranteed_ivs: u8, init_spawn: bool, max_advances: i32, slot_total: u64, shiny_filter_check: bool, slot_filter_check: bool, min_slot_filter: u64, max_slot_filter: u64, alpha_outbreak_filter: bool) -> (i32, f64, i64, i64, Vec<i8>, i8, i16, i8, bool) {
    let mut rng = Xoroshiro::new(group_seed);
    if !init_spawn {
        rng.next();
        rng.next();
        rng = Xoroshiro::new(rng.next_u64());
    }
    let mut adv = -1;
    if slot_total == 0 {
        return (-1,-1.0,-1,-1,vec![],-1,-1,-1,false);
    }

    loop {
        adv += 1;
        if adv > max_advances {
            return (-2,-1.0,-1,-1,vec![],-1,-1,-1,false);
        }
        let generator_seed = rng.next_u64();
        rng.next_u64();
        let mut rng2 = Xoroshiro::new(generator_seed);
        let slot = (rng2.next_u64() as f64 / 2_f64.powf(64.0)) * slot_total as f64;
        let (ec, pid, ivs, ability, gender, nature, shiny) = generate_from_seed(rng2.next_u64(), rolls, guaranteed_ivs);
        if !((shiny_filter_check && !shiny) || slot_filter_check && !((min_slot_filter as f64) <= slot && slot < (max_slot_filter as f64)) || alpha_outbreak_filter && !(100.0 <= slot && slot < 101.0)) {
            return (adv, slot, ec as i64, pid as i64, ivs.iter().map(|i| *i).collect::<Vec<i8>>(), ability as i8, gender as i16, nature as i8, shiny);
        }
        rng = Xoroshiro::new(rng.next_u64());
    }
}

#[pyfunction]
#[pyo3(name = "next_filtered")]
fn next_filtered_py(group_seed: u64, rolls: u8, guaranteed_ivs: u8, init_spawn: bool, max_advances: i32, slot_total: u64, shiny_filter_check: bool, slot_filter_check: bool, min_slot_filter: u64, max_slot_filter: u64, alpha_outbreak_filter: bool) -> PyResult<(i32, f64, i64, i64, Vec<i8>, i8, i16, i8, bool)> {
    Ok(next_filtered(group_seed, rolls, guaranteed_ivs, init_spawn, max_advances, slot_total, shiny_filter_check, slot_filter_check, min_slot_filter, max_slot_filter, alpha_outbreak_filter))
}

#[pyfunction]
fn generate_from_seed(seed: u64, rolls: u8, guaranteed_ivs: u8) -> (u32, u32, [i8; 6], u8, u8, u8, bool) {
    let mut rng = Xoroshiro::new(seed);
    let ec = rng.next();
    let sidtid = rng.next();
    let mut pid: u32 = 0;
    let mut shiny = false;
    for _ in 0..rolls {
        pid = rng.next();
        shiny = ((pid >> 16) ^ (sidtid >> 16) ^ (pid & 0xFFFF) ^ (sidtid & 0xFFFF)) < 0x10;
        if shiny {
            break;
        }
    }
    let mut ivs: [i8; 6] = [-1, -1, -1, -1, -1, -1];
    for _ in 0..guaranteed_ivs {
        let mut index = rng.rand_max(6);
        while ivs[index as usize] != -1 {
            index = rng.rand_max(6);
        }
        ivs[index as usize] = 31;
    }

    for i in 0..6 {
        if ivs[i] == -1 {
            ivs[i] = rng.rand_max(32) as i8;
        }
    }

    let ability = rng.rand_max(2) as u8;

    let gender = (rng.rand_max(252) + 1) as u8;

    let nature = rng.rand_max(25) as u8;

    (ec, pid, ivs, ability, gender, nature, shiny)
}

fn calc_from_seed(seed: u64, init_spawn: bool, slot_total: u64, rolls: u8, guaranteed_ivs: u8) -> (u32, u32, [i8; 6], u8, u8, u8, bool, f64) {
    let mut rng = Xoroshiro::new(seed);
    if !init_spawn {
        rng.next();
        rng.next();
        rng = Xoroshiro::new(rng.next_u64());
    }
    rng = Xoroshiro::new(rng.next_u64());
    let slot = ((rng.next_u64() as f64 / 2_f64.powf(64.0)) * slot_total as f64) as f64;
    let fixed_seed = rng.next_u64();
    let (ec, pid, ivs, ability, gender, nature, shiny) = generate_from_seed(fixed_seed, rolls, guaranteed_ivs);
    (ec, pid, ivs, ability, gender, nature, shiny, slot)
}

#[pyfunction]
#[pyo3(name = "calc_from_seed")]
fn calc_from_seed_py(seed: u64, init_spawn: bool, slot_total: u64, rolls: u8, guaranteed_ivs: u8) -> PyResult<(u32, u32, [i8; 6], u8, u8, u8, bool, f64)> {
    let out = calc_from_seed(seed, init_spawn, slot_total, rolls, guaranteed_ivs);
    Ok(out)
}

fn generate_mass_outbreak_passive_path(group_seed: u64, rolls: u8, steps: Vec<i32>, total_spawns: u32, shiny_filter_check: bool, outbreak_alpha_filter: bool, filtered_results_info: &mut HashMap<u64, String>, filtered_results_paths: &mut HashMap<u64, Vec<Vec<i32>>>) -> bool {
    let mut rng = Xoroshiro::new(group_seed);
    let mut passes_filters = false;

    for (step_i, step) in steps.iter().enumerate() {
        let left = total_spawns as i32 - steps[..step_i+1].iter().sum::<i32>();
        let final_in_init = (step_i == steps.len() - 1) && left + *step <= 4;
        let all_in_init = (step_i != steps.len() - 1) && left <= 4;
        let down_to_init = final_in_init || all_in_init;
        let mut add = 0;
        if !final_in_init {
            add = left.min(4);
        }
        for pokemon in 0..(*step + add) as i32{
            let spawner_seed = rng.next_u64();
            let mut spawner_rng = Xoroshiro::new(spawner_seed);
            let slot = spawner_rng.next_u64() as f64 / (2_f64.powi(64)) * 101.0;
            let alpha = slot >= 100.0;
            let fixed_seed = spawner_rng.next_u64();
            let (ec, pid, ivs, ability, gender, nature, shiny) = generate_from_seed(fixed_seed, rolls, if alpha { 3 } else { 0 });
            let filtered = (shiny_filter_check && !shiny) || (outbreak_alpha_filter && !alpha);
            passes_filters |= !filtered;
            if !filtered {
                let effective_path = [&steps[..step_i], &[0_i32.max(pokemon - 3)][..]].concat();
                //println!("{}", effective_path.iter().map(|i| i.to_string()).collect::<Vec<String>>().join("|"));
                if filtered_results_info.contains_key(&fixed_seed) && !filtered_results_paths.get(&fixed_seed).unwrap().contains(&effective_path) {
                    filtered_results_paths.entry(fixed_seed).or_insert(vec![]).push(effective_path);
                } else {
                    *filtered_results_paths.entry(fixed_seed).or_insert(vec![]) = vec![effective_path];
                    *filtered_results_info.entry(fixed_seed).or_insert(String::new()) = format!("<b>Shiny: <font color=\"{}\">{shiny}</font></b><br><b>Alpha: <font color=\"{}\">{alpha}</font></b></br>EC: {ec:08X} PID: {pid:08X}<br>Nature: {nature} Ability: {ability} Gender: {gender}<br>{}", {if shiny { "green" } else { "red" }}, {if alpha { "green" } else { "red" }}, { ivs.iter().map(|i| i.to_string()).collect::<Vec<String>>().join("/") }, ec = ec, pid = pid, nature = nature, gender = gender, ability = ability).to_string();
                }
            }
            rng.next();
            if !down_to_init && pokemon >= 3 {
                rng = Xoroshiro::new(rng.next_u64());
            }
        }
    }

    passes_filters
}

#[pyfunction]
fn generate_passive_search_paths(group_seed: u64, rolls: u8, spawns: u32, move_limit: u32, shiny_filter_check: bool, outbreak_alpha_filter: bool, exhaustive_search: bool) -> PyResult<(HashMap<u64, String>, HashMap<u64, Vec<Vec<i32>>>)> {
    let mut stack: Vec<(i32, Vec<i32>)> = Vec::new();
    let mut info: HashMap<u64, String> = HashMap::new();
    let mut paths: HashMap<u64, Vec<Vec<i32>>> = HashMap::new();

    let work = spawns * (spawns + 3);

    for i in 0..spawns + 1 {
        stack.push((spawns as i32 - 4 - i as i32, vec![i as i32]));
    }

    while stack.len() > 0 {
        let (spawns_left, path) = stack.pop().unwrap();
        if spawns_left <= 0 || path.len() > move_limit as usize {
            continue;
        }

        if !exhaustive_search && path.len() * (spawns + 1) as usize > work as usize {
            break;
        }


        let passes_filter = generate_mass_outbreak_passive_path(group_seed, rolls, path.clone(), spawns, shiny_filter_check, outbreak_alpha_filter, &mut info, &mut paths);

        let c_work = path.len() as u32 * (spawns + 1) + path.iter().sum::<i32>() as u32;
        if passes_filter && c_work < work {
            if !exhaustive_search {
                return Ok((info, paths));
            }
        }

        if path.len() == move_limit as usize {
            continue;
        }

        for i in 0..spawns_left+1 {
            let mut path_ = path.clone();
            path_.push(i);
            stack.push((spawns_left - i, path_));
        }
    }
    Ok((info, paths))
}

#[cfg(test)]
mod test {
    use std::collections::HashMap;
    use std::hash::Hash;
    use crate::{calc_from_seed_py, find_slots, generate_from_seed, generate_passive_search_paths};

    #[test]
    fn test_seed() {
        assert_eq!(generate_from_seed(0x863537112D0E2E56, 1, 0), (1336645809, 1065431661, [3, 29, 14, 1, 8, 11], 0, 207, 0, false));
    }

    #[test]
    fn test_seed_with_guaranteed_ivs() {
        assert_eq!(generate_from_seed(0x863537112D0E2E56, 1, 3), (1336645809, 1065431661, [8, 31, 11, 31, 18, 31], 0, 220, 0, false));
    }

    #[test]
    fn test_seed_with_extra_shiny_rolls() {
        assert_eq!(generate_from_seed(0x863537112D0E2E56, 5, 3), (1336645809, 207309409, [31, 14, 31, 31, 27, 29], 0, 1, 20, false));
    }

    #[test]
    fn test_passive_search() {
        let (info, paths) = generate_passive_search_paths(0x52DAA9F68EB2C623, 26, 10, 10, true, false, true).unwrap();
        for path in paths {
            println!("{:X} {}", path.0, path.1.iter().map(|i| i.iter().map(|i| i.to_string()).collect::<Vec<String>>().join("|")).collect::<Vec<String>>().join("\n"));
        }

        for infos in &info {
            println!("{:X} {}", infos.0, infos.1);
        }
        assert!(info.len() < 1);
    }

}